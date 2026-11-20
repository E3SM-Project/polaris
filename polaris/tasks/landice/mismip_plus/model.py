from polaris.landice.mismip_plus.geometry import ICE_DENSITY, OCEAN_DENSITY
from polaris.landice.model import MaliModelStep


class MismipPlusModelStep(MaliModelStep):
    """
    A step for running MALI on the MISMIP+ mesh with the first-order velocity
    solver
    """

    def __init__(
        self,
        component,
        name,
        subdir=None,
        indir=None,
        restart_interval='0050-00-00_00:00:00',
        output_interval='none',
        output_clobber_mode='truncate',
    ):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        name : str
            The name of the step

        subdir : str, optional
            the subdirectory for the step.  If neither this nor ``indir``
            are provided, the directory is the ``name``

        indir : str, optional
            the directory the step is in, to which ``name`` will be appended

        restart_interval : str, optional
            The interval between restarts

        output_interval : str, optional
            The interval between snapshots in ``output.nc``, or ``none``

        output_clobber_mode : str, optional
            How MALI treats an existing ``output.nc``: ``truncate`` to start
            it again or ``overwrite`` to add to it
        """
        super().__init__(
            component=component,
            name=name,
            subdir=subdir,
            indir=indir,
            openmp_threads=1,
            velocity_solver='FO',
            albany_input_package='polaris.tasks.landice.mismip_plus',
        )

        package = 'polaris.tasks.landice.mismip_plus'
        self.add_namelist_file(package, 'namelist.landice')
        self.add_streams_file(
            package,
            'streams.landice',
            template_replacements={
                'restart_interval': restart_interval,
                'output_interval': output_interval,
                'output_clobber_mode': output_clobber_mode,
            },
        )
        self.add_output_file(filename='globalStats.nc')

    def setup(self):
        """
        Set the number of MPI tasks from config options
        """
        self._update_ntasks()
        super().setup()

    def constrain_resources(self, available_resources):
        """
        Update the number of MPI tasks from config options, then constrain them
        to the available resources

        Parameters
        ----------
        available_resources : dict
            A dictionary containing available resources (cores, tasks, nodes
            and cores_per_node)
        """
        self._update_ntasks()
        super().constrain_resources(available_resources)

    def dynamic_model_config(self, at_setup):
        """
        Set the rate factor from config options and the protocol's densities

        Parameters
        ----------
        at_setup : bool
            Whether this method is being run during setup of the step, as
            opposed to at runtime
        """
        super().dynamic_model_config(at_setup)
        flow_param_a = self.config.getfloat('mismip_plus', 'flow_param_a')
        # Albany takes the rate factor from MALI, since the Albany input file
        # does not set it
        self.add_model_config_options(
            options={
                'config_default_flowParamA': flow_param_a,
                'config_ice_density': ICE_DENSITY,
                'config_ocean_density': OCEAN_DENSITY,
            }
        )

    def _update_ntasks(self):
        """
        Set the number of MPI tasks from config options
        """
        section = self.config['mismip_plus']
        self.ntasks = section.getint('ntasks')
        self.min_tasks = section.getint('min_tasks')
