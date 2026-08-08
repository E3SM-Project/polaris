import os
from typing import Optional

from polaris.ocean.model import OceanModelStep
from polaris.tasks.ocean.realistic_global.forward.initial_condition import (
    InitialCondition,
)
from polaris.tasks.ocean.realistic_global.forward.stage import ForwardStage


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
        The Jinja2 template that points each model's input stream at the staged
        forcing file.  Only added when ``init_condition`` stages one.
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
        output_filename='output.nc',
        validate_vars=None,
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
            used only when ``init_condition`` stages a forcing file.

        output_filename : str, optional
            The output file written at the end of the run.

        validate_vars : list of str, optional
            Variables in ``output_filename`` to validate against a baseline.

        check_properties : list of str, optional
            Conservation properties of ``output_filename`` to check.

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

        # ensure the model output is written in double precision
        self.add_yaml_file('polaris.ocean.config', 'output.yaml')

        self.add_output_file(
            filename=output_filename,
            validate_vars=validate_vars,
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

        The restart filenames are declared for MPAS-Ocean only.  Omega names
        its restart streams without a ``.nc`` extension, and whether it appends
        one has not been verified against a build, so declaring a filename
        there would risk failing every stage on a guess.  See the Omega block
        of ``restart_streams.yaml``.
        """
        self.init_condition.add_input_files(self)
        stage = self.stage
        model = self.config.get('ocean', 'model')
        if stage is not None and model == 'mpas-ocean':
            if stage.restart_in is not None:
                self.add_input_file(filename=f'../{stage.restart_in}')
            if stage.restart_out is not None:
                self.add_output_file(filename=f'../{stage.restart_out}')
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
        Render ``forward.yaml`` from the stage and apply MPAS-Ocean damping.

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

        if not at_setup:
            # deferred to run time, as the time-integrator check is, so that a
            # user can set the task up and then change the model or the
            # schedule
            stage.check_damping_supported(model)

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

        # the input streams, in contrast, are only added when the model reads
        # its forcing from a staged file, since MPAS-Ocean aborts when an input
        # stream names a file that is not there.  Which file that is belongs to
        # the initial condition: a database source carries the wind stress in
        # the initial-condition file rather than one of its own.
        if self.init_condition.provides_forcing_file:
            self.add_yaml_file(
                self.package,
                self.forcing_streams_yaml_filename,
                template_replacements=dict(
                    forcing_filename=self.init_condition.get_forcing_filename(
                        self
                    )
                ),
            )

        # horizontal mixing is supported by both models, so it is added in
        # MPAS-Ocean naming and translated to Omega by OceanModelStep
        self.add_model_config_options(
            options=stage.horiz_mixing_options(), config_model='ocean'
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

    def _mesh_path(self):
        """
        The path to the mesh input file, or ``None`` when it does not yet
        exist.
        """
        if self.work_dir is None:
            return None
        mesh_path = os.path.join(self.work_dir, self.get_horiz_mesh_filename())
        return mesh_path if os.path.exists(mesh_path) else None
