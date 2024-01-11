from polaris.mesh.planar import compute_planar_hex_nx_ny
from polaris.ocean.model import OceanModelStep, get_time_interval_string


class SshForward(OceanModelStep):
    """
    A step for performing forward ocean component runs as part of baroclinic
    channel tasks.

    Attributes
    ----------
    resolution : float
        The resolution of the task in km

    package : Package
        The package name or module object that contains ``namelist``

    yaml_filename : str, optional
        the yaml filename used for ssh_forward steps

    yaml_replacements : Dict, optional
        key, string combinations for templated replacements in the yaml
        file
    """
    def __init__(self, component, resolution, mesh, init,
                 name='ssh_forward', subdir=None,
                 package=None, yaml_filename='ssh_forward.yaml',
                 yaml_replacements=None, iteration=1, indir=None,
                 ntasks=None, min_tasks=None, openmp_threads=1):
        """
        Create a new task

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        resolution : km
            The resolution of the task in km

        name : str
            the name of the task

        mesh: polaris.Step
            The step used to produce the mesh

        init: polaris.Step
            The step used to produce the initial condition

        subdir : str, optional
            the subdirectory for the step.  If neither this nor ``indir``
             are provided, the directory is the ``name``

        package : str, optional
            where ssh_forward steps will derive their configuration

        yaml_filename : str, optional
            the yaml filename used for ssh_forward steps

        yaml_replacements : Dict, optional
            key, string combinations for templated replacements in the yaml
            file

        iteration : int, optional
            the iteration number

        indir : str, optional
            the directory the step is in, to which ``name`` will be appended

        ntasks : int, optional
            the number of tasks the step would ideally use.  If fewer tasks
            are available on the system, the step will run on all available
            tasks as long as this is not below ``min_tasks``

        min_tasks : int, optional
            the number of tasks the step requires.  If the system has fewer
            than this number of tasks, the step will fail

        openmp_threads : int, optional
            the number of OpenMP threads the step will use
        """
        super().__init__(component=component, name=name, subdir=subdir,
                         indir=f'{indir}/ssh_adjustment', ntasks=ntasks,
                         min_tasks=min_tasks, openmp_threads=openmp_threads)

        self.resolution = resolution
        self.package = package
        self.yaml_filename = yaml_filename
        self.yaml_replacements = yaml_replacements

        # make sure output is double precision
        self.add_yaml_file('polaris.ocean.config', 'output.yaml')

        self.add_input_file(filename='init.nc',
                            work_dir_target=f'{init.path}/output.nc')
        self.add_input_file(filename='graph.info',
                            work_dir_target=f'{mesh.path}/culled_graph.info')

        self.add_output_file(
            filename='output.nc',
            validate_vars=['temperature', 'salinity', 'layerThickness',
                           'normalVelocity'])

    def compute_cell_count(self):
        """
        Compute the approximate number of cells in the mesh, used to constrain
        resources

        Returns
        -------
        cell_count : int or None
            The approximate number of cells in the mesh
        """
        section = self.config['ice_shelf_2d']
        lx = section.getfloat('lx')
        ly = section.getfloat('ly')
        nx, ny = compute_planar_hex_nx_ny(lx, ly, self.resolution)
        cell_count = nx * ny
        return cell_count

    def dynamic_model_config(self, at_setup):
        """
        Add model config options, namelist, streams and yaml files using config
        options or template replacements that need to be set both during step
        setup and at runtime

        Parameters
        ----------
        at_setup : bool
            Whether this method is being run during setup of the step, as
            opposed to at runtime
        """
        super().dynamic_model_config(at_setup)

        config = self.config

        vert_levels = config.getfloat('vertical_grid', 'vert_levels')
        if not at_setup and vert_levels == 1:
            self.add_yaml_file('polaris.ocean.config', 'single_layer.yaml')

        section = config['ssh_adjustment']

        # dt is proportional to resolution: default 30 seconds per km
        time_integrator = section.get('time_integrator')

        if time_integrator == 'RK4':
            dt_per_km = section.getfloat('rk4_dt_per_km')
        else:
            dt_per_km = section.getfloat('split_dt_per_km')
        dt_str = get_time_interval_string(seconds=dt_per_km * self.resolution)

        # btr_dt is also proportional to resolution: default 1.5 seconds per km
        btr_dt_per_km = section.getfloat('btr_dt_per_km')
        btr_dt_str = get_time_interval_string(
            seconds=btr_dt_per_km * self.resolution)

        s_per_hour = 3600.
        run_duration = section.getfloat('run_duration')
        run_duration_str = get_time_interval_string(
            seconds=run_duration * s_per_hour)

        output_interval = section.getfloat('output_interval')
        output_interval_str = get_time_interval_string(
            seconds=output_interval * s_per_hour)

        replacements = dict(
            dt=dt_str,
            btr_dt=btr_dt_str,
            time_integrator=time_integrator,
            run_duration=run_duration_str,
            output_interval=output_interval_str,
        )

        self.add_yaml_file('polaris.ocean.ice_shelf',
                           'ssh_forward.yaml',
                           template_replacements=replacements)
        if self.package is not None:
            self.add_yaml_file(package=self.package,
                               yaml=self.yaml_filename,
                               template_replacements=self.yaml_replacements)
