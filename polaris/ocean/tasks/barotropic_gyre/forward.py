import time
from math import ceil

from polaris.mesh.planar import compute_planar_hex_nx_ny
from polaris.ocean.model import OceanModelStep, get_time_interval_string


class Forward(OceanModelStep):
    """
    A step for performing forward ocean component runs as part of barotropic
    gyre tasks.

    Attributes
    ----------
    resolution : float
        The resolution of the task in km

    dt : float
        The model time step in seconds

    run_time_steps : int or None
        Number of time steps to run for
    """
    def __init__(self, component, name='forward', subdir=None,
                 indir=None, ntasks=None, min_tasks=None, openmp_threads=1,
                 nu=None, run_time_steps=None, graph_target='graph.info'):
        """
        Create a new task

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        name : str
            the name of the task

        subdir : str, optional
            the subdirectory for the step.  If neither this nor ``indir``
             are provided, the directory is the ``name``

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

        run_time_steps : int or None
            Number of time steps to run for

        graph_target : str, optional
            The graph file name (relative to the base work directory).
            If none, it will be created.
        """
        self.run_time_steps = run_time_steps
        super().__init__(component=component, name=name, subdir=subdir,
                         indir=indir, ntasks=ntasks, min_tasks=min_tasks,
                         openmp_threads=openmp_threads,
                         graph_target=graph_target)

        # make sure output is double precision
        self.add_yaml_file('polaris.ocean.config', 'output.yaml')

        self.add_input_file(filename='init.nc',
                            target='../init/init.nc')
        self.add_input_file(filename='forcing.nc',
                            target='../init/forcing.nc')

        self.add_output_file(
            filename='output.nc',
            validate_vars=['temperature', 'salinity', 'layerThickness',
                           'normalVelocity'])

        self.package = 'polaris.ocean.tasks.barotropic_gyre'
        self.yaml_filename = 'forward.yaml'

    def compute_cell_count(self):
        """
        Compute the approximate number of cells in the mesh, used to constrain
        resources

        Returns
        -------
        cell_count : int or None
            The approximate number of cells in the mesh
        """
        section = self.config['barotropic_gyre']
        lx = section.getfloat('lx')
        resolution = section.getfloat('resolution')
        ly = section.getfloat('ly')
        nx, ny = compute_planar_hex_nx_ny(lx, ly, resolution)
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

        model = config.get('ocean', 'model')
        if model == 'mpas-ocean':
            self.add_yaml_file('polaris.ocean.config', 'single_layer.yaml')

        nu = config.getfloat("barotropic_gyre", "nu_2")
        rho_0 = config.getfloat("barotropic_gyre", "rho_0")

        dt_max = compute_max_time_step(config)
        dt = dt_max / 3.
        dt_str = get_time_interval_string(seconds=dt)

        options = {'config_dt': dt_str,
                   'config_density0': rho_0}
        self.add_model_config_options(options=options,
                                      config_model='mpas-ocean')

        if self.run_time_steps is not None:
            run_duration = ceil(self.run_time_steps * dt)
            stop_time_str = time.strftime('0001-01-01_%H:%M:%S',
                                          time.gmtime(run_duration))
            output_interval_str = time.strftime('0000_%H:%M:%S',
                                                time.gmtime(run_duration))
        else:
            stop_time_str = time.strftime('0004-01-01_00:00:00')
            output_interval_str = time.strftime('0000-01-00_00:00:00')

        replacements = dict(
            dt=dt_str,
            stop_time=stop_time_str,
            output_interval=output_interval_str,
            nu=f'{nu:02g}',
        )

        # make sure output is double precision
        self.add_yaml_file(self.package, self.yaml_filename,
                           template_replacements=replacements)


def compute_max_time_step(config):
    u_max = 1  # m/s
    stability_parameter_max = 0.25
    resolution = config.getfloat('barotropic_gyre', 'resolution')
    f_0 = config.getfloat("barotropic_gyre", "f_0")
    dt_max = min(stability_parameter_max * resolution * 1e3 /
                 (2 * u_max),
                 stability_parameter_max / f_0)
    return dt_max
