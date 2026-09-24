import os

from polaris.ocean.model import OceanModelStep


class Forward(OceanModelStep):
    """
    A step for performing forward ocean component runs as part of the cosine
    bell test case
    """

    def __init__(
        self,
        component,
        package,
        mesh_name,
        mpaso_id,
        omega_id,
        ncells=None,
        name='forward',
        indir=None,
        subdir=None,
        update_eos=False,
        output_filenames=None,
        ntasks=None,
        min_tasks=None,
        options=None,
        replacements=None,
        validate_vars=None,
        check_properties=None,
    ):
        """
        Create a new step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        name : str
            The name of the step

        subdir : str
            The subdirectory for the step

        output_filenames : list of str, optional
            The files the run writes, relative to the step's work directory,
            each declared as an output; ``output.nc`` by default
        """
        if output_filenames is None:
            output_filenames = ['output.nc']
        super().__init__(
            component=component,
            name=name,
            indir=indir,
            subdir=subdir,
            ntasks=ntasks,
            min_tasks=min_tasks,
            update_eos=update_eos,
            openmp_threads=1,
            graph_target=f'graph.info.{mpaso_id}',
        )
        self.mesh_name = mesh_name
        self.mpaso_id = mpaso_id
        self.omega_id = omega_id
        self.ncells = ncells
        self.replacements = replacements
        self.package = package
        # the directories Omega's streams write into, which Omega does not
        # create itself; a subclass whose streams write elsewhere adds to it
        self.stream_dirs = ['restart']
        # make sure output is double precision
        self.add_yaml_file('polaris.ocean.config', 'output.yaml')

        if options is not None:
            for config_model in options:
                self.add_model_config_options(
                    options=options[config_model], config_model=config_model
                )

        # TODO replace validate_vars with all model-specific state vars
        for output_filename in output_filenames:
            self.add_output_file(
                filename=output_filename,
                validate_vars=validate_vars,
                check_properties=check_properties,
            )

    def setup(self):
        """
        TEMP: symlink initial condition to name hard-coded in Omega
        """
        config = self.config
        model = config.get('ocean', 'model')
        # This attribute is used by OceanModelStep
        target_location = f'realistic_global/{model}/{self.mesh_name}'
        self.target_location = target_location
        super().setup()
        # TODO: remove as soon as Omega no longer hard-codes this file
        input_filename = f'ocean.{self.mesh_name}.{self.mpaso_id}'
        if model == 'omega':
            # Currently, only TEOS-10 is supported
            eos_type = 'teos10'
            input_filename = f'{input_filename}.{eos_type}.{self.omega_id}.nc'
            self.add_input_file(
                target=input_filename,
                filename='mesh.nc',
                database=target_location,
            )
            self.add_input_file(
                target=input_filename,
                filename='vert_coord.nc',
                database=target_location,
            )
            self.add_input_file(
                target=input_filename,
                filename='init.nc',
                database=target_location,
            )
        else:
            self.replacements['time_integrator'] = 'RK4'
            input_filename = f'{input_filename}.zerovel.nc'
            self.add_input_file(
                target=input_filename,
                filename='mesh.nc',
                database=target_location,
            )
            self.add_input_file(
                target=input_filename,
                filename='init.nc',
                database=target_location,
            )
        self.add_yaml_file(
            package=self.package,
            yaml='forward.yaml',
            template_replacements=self.replacements,
        )
        self._make_stream_dirs()

    def runtime_setup(self):
        """
        Make sure the stream directories exist before the model runs
        """
        super().runtime_setup()
        self._make_stream_dirs()

    def _make_stream_dirs(self):
        """
        Create the directories Omega's streams write into, ``restart`` for
        the ``RestartWrite`` stream unless a subclass adds more.

        Omega does not create them, so without this the restart write fails
        at the end of the run and the run cannot be continued.  MPAS-Ocean
        needs no equivalent: the MPAS framework creates stream directories
        itself (``xml_stream_parser.c``).  The paths match the ``Filename``
        of each stream under ``IOStreams`` in the step's yaml files.
        """
        if self.config.get('ocean', 'model') != 'omega':
            return
        for dirname in self.stream_dirs:
            os.makedirs(os.path.join(self.work_dir, dirname), exist_ok=True)

    def compute_cell_count(self):
        """
        Compute the approximate number of cells in the mesh, used to constrain
        resources

        Returns
        -------
        cell_count : int or None
            The approximate number of cells in the mesh
        """
        if self.ncells is None:
            raise ValueError(
                'Cell count is required for realistic_global tests'
            )
        return self.ncells
