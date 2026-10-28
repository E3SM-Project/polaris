import os
from typing import List, Optional

import numpy as np

from polaris.ocean.model import OceanModelStep
from polaris.tasks.ocean.realistic_global.forward.initial_condition import (
    InitialCondition,
)
from polaris.tasks.ocean.realistic_global.forward.stage import (
    ForwardStage,
    omega_median_cell_width,
)


class Forward(OceanModelStep):
    """
    A forward run of the configured ocean model for a realistic global ocean
    simulation.

    The step gets its model inputs from an :py:class:`InitialCondition` and its
    run settings from a :py:class:`ForwardStage`.  All MPAS-Ocean-vs-Omega
    branching is handled by :py:class:`~polaris.ocean.model.OceanModelStep` and
    the single mapping in ``ForwardStage.model_replacements``.

    Attributes
    ----------
    init_condition : InitialCondition
        The source of the model input files.

    stage : ForwardStage or None
        The model-agnostic settings for this run.  When ``None``, they are
        built from the ``[realistic_global_forward]`` config section at setup
        and run time (so user config overrides take effect).

    package : str
        The package that contains ``yaml_filename``.

    yaml_filename : str
        The Jinja2 model-config template rendered from ``stage``.

    forcing_yaml_filename : str
        The model-config file that turns the wind forcing on.  Always added.

    forcing_streams_yaml_filename : str
        The Jinja2 template that points each model's input stream at the file
        that holds the wind stress, which ``init_condition`` names.  Always
        added.

    stream_dirs : list of str
        Directories, relative to the step's work directory, that Omega's
        streams write into.  Omega does not create them, so the step does,
        at setup and again at run time.  MPAS-Ocean needs no equivalent,
        since the MPAS framework creates stream directories itself.  Empty
        unless a task's yaml files point a stream into a subdirectory.
    """

    def __init__(
        self,
        component,
        init_condition: InitialCondition,
        stage: Optional[ForwardStage] = None,
        name='forward',
        subdir=None,
        indir=None,
        package='polaris.tasks.ocean.realistic_global.forward',
        yaml_filename='forward.yaml',
        forcing_yaml_filename='forcing.yaml',
        forcing_streams_yaml_filename='forcing_streams.yaml',
        output_filenames: Optional[List[str]] = None,
        validate_vars=None,
        validate_class=None,
        check_properties=None,
        update_eos=False,
    ):
        """
        Create the step.

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the step belongs to.

        init_condition : InitialCondition
            The source of the model input files (a database file or an upstream
            ``realistic_global/init`` step).

        stage : ForwardStage, optional
            The model-agnostic run settings.  When not provided, they are built
            from the ``[realistic_global_forward]`` config section.

        name : str, optional
            The name of the step.

        subdir : str, optional
            The subdirectory for the step.

        indir : str, optional
            The directory the step is in, to which ``name`` is appended (used
            when ``subdir`` is not provided).

        package : str, optional
            The package that contains ``yaml_filename``.

        yaml_filename : str, optional
            A YAML file that is a Jinja2 template of model config options.

        forcing_yaml_filename : str, optional
            A YAML file of the wind-forcing model config options, always added.

        forcing_streams_yaml_filename : str, optional
            A YAML file that is a Jinja2 template of the forcing input streams,
            always added.

        output_filenames : list of str, optional
            The files the run writes, relative to the step's work directory,
            each declared as an output; ``output.nc`` by default.

        validate_vars : list of str, optional
            Variables in each output file to validate against a baseline.

        validate_class : str, optional
            A named class of variables from ``variables.yaml`` to validate in
            each output file, such as ``'state'``, in addition to
            ``validate_vars``.

        check_properties : list of str, optional
            Conservation properties of each output file to check.

        update_eos : bool, optional
            Whether to update the equation of state from config options.
        """
        super().__init__(
            component=component,
            name=name,
            subdir=subdir,
            indir=indir,
            openmp_threads=1,
            update_eos=update_eos,
            graph_target=init_condition.graph_target,
        )
        self.init_condition = init_condition
        self.stage = stage
        self.package = package
        self.yaml_filename = yaml_filename
        self.forcing_yaml_filename = forcing_yaml_filename
        self.forcing_streams_yaml_filename = forcing_streams_yaml_filename
        self.stream_dirs: List[str] = []

        # ensure the model output is written in double precision
        self.add_yaml_file('polaris.ocean.config', 'output.yaml')

        if output_filenames is None:
            output_filenames = ['output.nc']
        for output_filename in output_filenames:
            self.add_output_file(
                filename=output_filename,
                validate_vars=validate_vars,
                validate_class=validate_class,
                check_properties=check_properties,
            )

    def setup(self):
        """
        Add the initial-condition input files, then set up the model step.

        When the step's stage is part of a restart chain, the restart it reads
        (``restart_in``) and the one it writes (``restart_out``) in the shared
        ``restarts`` directory are declared as an input and an output.  Both
        paths are relative to the task work directory rather than the step's,
        since the whole point of the directory is that the stages share it.
        Declaring them is what makes the chain explicit to Polaris: a stage
        whose predecessor did not produce its restart fails before the model
        launches, rather than aborting inside it.

        Omega writes each stage's restart into a directory of its own, so the
        files declared for Omega are the ones in those directories; see
        :py:meth:`ForwardStage.restart_files`.
        """
        self.init_condition.add_input_files(self)
        stage = self.stage
        model = self.config.get('ocean', 'model')
        if stage is not None:
            restart_in, restart_out = stage.restart_files(model)
            if restart_in is not None:
                self.add_input_file(filename=restart_in)
            if restart_out is not None:
                self.add_output_file(filename=restart_out)
        super().setup()

    def compute_cell_count(self):
        """
        Compute the number of cells used to size resources.

        Returns the exact ``nCells`` from the mesh once it exists (at run
        time), and otherwise the initial condition's ``approx_cell_count``
        estimate (during setup, before the upstream initial condition has been
        produced).

        Returns
        -------
        cell_count : int
            The number of cells in the mesh.
        """
        mesh_path = self._mesh_path()
        if mesh_path is not None:
            ds = self.component.open_model_dataset(mesh_path, self.config)
            return int(ds.sizes['nCells'])
        approx = self.init_condition.approx_cell_count
        if approx is None:
            raise ValueError(
                'approx_cell_count could not be determined for this mesh; '
                'pass it explicitly on the InitialCondition.'
            )
        return int(approx)

    def dynamic_model_config(self, at_setup):
        """
        Render ``forward.yaml`` from the stage and add the physics options.

        Parameters
        ----------
        at_setup : bool
            Whether this is being run during setup of the step, as opposed to
            at run time.
        """
        super().dynamic_model_config(at_setup=at_setup)

        config = self.config
        model = config.get('ocean', 'model')
        min_res = self.init_condition.min_res

        stage = self.stage
        if stage is None:
            stage = ForwardStage.from_config(config)

        replacements = stage.model_replacements(
            model, min_res, at_setup=at_setup
        )
        self.add_yaml_file(
            self.package,
            self.yaml_filename,
            template_replacements=replacements,
        )

        # every realistic_global forward run is wind-forced; there is no option
        # to turn it off
        self.add_yaml_file(self.package, self.forcing_yaml_filename)

        # which file holds the wind stress belongs to the initial condition: a
        # database source carries it in the initial-condition file rather
        # than one of its own
        self.add_yaml_file(
            self.package,
            self.forcing_streams_yaml_filename,
            template_replacements=dict(
                forcing_filename=self.init_condition.get_forcing_filename(self)
            ),
        )

        # horizontal mixing, the KPP boundary layer and the submesoscale eddy
        # parameterization are supported by both models, so they are added in
        # MPAS-Ocean naming and translated to Omega by OceanModelStep.  Scaled
        # coefficients apply at hmix_ref_cell_width, which defaults to the
        # mesh's median cell width, Omega's own reference.  Omega's
        # coefficients are converted when the reference is something else.
        # The median needs the mesh, so before an init-chain mesh exists the
        # run-time call fills it in.
        mesh_widths = None
        if stage.hmix_scaling == 'ref_cell_width':
            mesh_widths = self._mesh_widths(at_setup)
        median_cell_width = None if mesh_widths is None else mesh_widths[0]
        stage = stage.with_median_reference(median_cell_width)
        horiz_mixing_options = stage.horiz_mixing_options(
            model, median_cell_width
        )
        if mesh_widths is not None and not at_setup:
            _log_hmix_scaling(
                self.logger, model, stage, mesh_widths, horiz_mixing_options
            )
        self.add_model_config_options(
            options=horiz_mixing_options, config_model='ocean'
        )
        self.add_model_config_options(
            options=stage.vert_mixing_options(), config_model='ocean'
        )
        self.add_model_config_options(
            options=stage.submesoscale_options(), config_model='ocean'
        )

        if model == 'omega':
            self.add_model_config_options(
                options=stage.omega_physics_options(), config_model='Omega'
            )
            damping = stage.omega_damping_replacements()
            if damping is not None:
                self.add_yaml_file(
                    self.package,
                    'omega_damping.yaml',
                    template_replacements=damping,
                )

        if model == 'omega' and self.work_dir is not None:
            # Omega does not make the directories its streams write into
            for dirname in self.stream_dirs:
                os.makedirs(
                    os.path.join(self.work_dir, dirname), exist_ok=True
                )

        if model == 'mpas-ocean':
            self.add_model_config_options(
                options=stage.mpaso_physics_options(),
                config_model='mpas-ocean',
            )
            options = stage.bottom_drag_options()
            if options:
                self.add_model_config_options(
                    options=options, config_model='ocean'
                )

        if stage.restart_out is not None:
            # this stage is part of a restart chain: write its restart to the
            # shared ``../restarts`` directory.  For MPAS-Ocean the read side
            # is config_do_restart / config_start_time from forward.yaml; Omega
            # needs a RestartRead stream, which the replacements switch on only
            # for a stage that is restarting.
            self.add_yaml_file(
                self.package,
                'restart_streams.yaml',
                template_replacements=stage.restart_stream_replacements(),
            )
            if self.work_dir is not None:
                restart_dir = os.path.join(self.work_dir, '..', 'restarts')
                os.makedirs(restart_dir, exist_ok=True)
                if model == 'omega':
                    # Omega writes into this directory but does not make it
                    os.makedirs(
                        os.path.join(
                            self.work_dir, stage.omega_restart_write_dir()
                        ),
                        exist_ok=True,
                    )

    def _mesh_path(self):
        """
        The path to the mesh input file, or ``None`` when it does not yet
        exist.
        """
        if self.work_dir is None:
            return None
        mesh_path = os.path.join(self.work_dir, self.get_horiz_mesh_filename())
        return mesh_path if os.path.exists(mesh_path) else None

    def _mesh_widths(self, at_setup):
        """
        The mesh's median cell width and the smallest and largest edge widths
        the mixing is scaled with (m), as Omega computes them, or ``None`` at
        setup when the mesh does not yet exist
        """
        mesh_path = self._mesh_path()
        if mesh_path is None:
            if at_setup:
                return None
            raise ValueError(
                'The mesh is needed at run time to compute the median cell '
                'width the horizontal mixing is scaled with, but '
                f'{self.get_horiz_mesh_filename()} was not found.'
            )
        ds = self.component.open_model_dataset(mesh_path, self.config)
        area_cell = ds.areaCell.values
        # 1-based in the file, with 0 for the missing cell of a boundary edge
        cells_on_edge = ds.cellsOnEdge.values - 1
        interior = np.all(cells_on_edge >= 0, axis=1)
        edge_widths = 2.0 * np.sqrt(
            area_cell[cells_on_edge[interior]].sum(axis=1) / (2.0 * np.pi)
        )
        return (
            omega_median_cell_width(area_cell),
            float(edge_widths.min()),
            float(edge_widths.max()),
        )


def _log_hmix_scaling(logger, model, stage, mesh_widths, options):
    """
    Log the reference and median cell widths and the coefficients, and for
    Omega the conversion and the range of mesh scaling factors, to compare
    with what Omega logs
    """
    median, edge_min, edge_max = mesh_widths
    ref = stage.hmix_ref_cell_width
    logger.info(
        f'Horizontal mixing scaled from a reference cell width of {ref:.6g} '
        f'm; the median cell width is {median:.6g} m'
    )
    if model == 'omega':
        ratio = stage.omega_hmix_ratio(model, median)
        del2_min = edge_min / median
        del2_max = edge_max / median
        logger.info(
            f'  for Omega, del2 coefficients are multiplied by {ratio:.6g} '
            f'and del4 by {ratio**3:.6g}\n'
            f'  expected MeshScalingDel2 min/max = '
            f'{del2_min:.6g}/{del2_max:.6g}\n'
            f'  expected MeshScalingDel4 min/max = '
            f'{del2_min**3:.6g}/{del2_max**3:.6g}'
        )
    for option in [
        'config_mom_del2',
        'config_mom_del4',
        'config_tracer_del2',
        'config_tracer_del4',
    ]:
        if option in options:
            logger.info(f'  {option} = {options[option]:.6g}')
