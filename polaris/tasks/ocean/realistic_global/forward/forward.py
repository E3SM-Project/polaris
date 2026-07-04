import os
from typing import Optional

import xarray as xr

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
        """
        self.init_condition.add_input_files(self)
        super().setup()

    def compute_cell_count(self):
        """
        Compute the number of cells used to size resources.

        Returns the exact ``nCells`` from the mesh once it exists (at run
        time), and otherwise the configured ``approx_cell_count`` (during
        setup, before the upstream initial condition has been produced).

        Returns
        -------
        cell_count : int
            The number of cells in the mesh.
        """
        mesh_path = self._mesh_path()
        if mesh_path is not None:
            with xr.open_dataset(mesh_path) as ds:
                return int(ds.sizes['nCells'])
        return self.config.getint(
            'realistic_global_forward', 'approx_cell_count'
        )

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

        replacements = stage.model_replacements(model, min_res)
        self.add_yaml_file(
            self.package,
            self.yaml_filename,
            template_replacements=replacements,
        )

        if model == 'mpas-ocean':
            options = stage.bottom_drag_options()
            if options:
                self.add_model_config_options(
                    options=options, config_model='ocean'
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
