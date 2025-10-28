import time
from math import ceil, floor, pi

import numpy as np

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

    def __init__(
        self,
        component,
        name='forward',
        subdir=None,
        indir=None,
        test_name='munk',
        boundary_condition='free slip',
        ntasks=None,
        min_tasks=None,
        openmp_threads=1,
        nu=None,
        run_time_steps=None,
        graph_target='graph.info',
    ):
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
        self.boundary_condition = boundary_condition
        super().__init__(
            component=component,
            name=name,
            subdir=subdir,
            indir=indir,
            ntasks=ntasks,
            min_tasks=min_tasks,
            openmp_threads=openmp_threads,
            graph_target=graph_target,
        )

        # make sure output is double precision
        self.add_yaml_file('polaris.ocean.config', 'output.yaml')

        self.add_input_file(filename='init.nc', target='../init/init.nc')
        self.add_input_file(filename='forcing.nc', target='../init/forcing.nc')

        self.add_output_file(
            filename='output.nc',
            validate_vars=['layerThickness', 'normalVelocity'],
        )

        self.package = 'polaris.tasks.ocean.barotropic_gyre'
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
        logger = self.logger

        model = config.get('ocean', 'model')
        vert_levels = config.getfloat('vertical_grid', 'vert_levels')
        if model == 'mpas-ocean' and vert_levels == 1:
            self.add_yaml_file('polaris.ocean.config', 'single_layer.yaml')

        resolution = config.getfloat('barotropic_gyre', 'resolution')
        # Laplacian viscosity
        nu = config.getfloat('barotropic_gyre', 'nu_2')
        rho_0 = config.getfloat('barotropic_gyre', 'rho_0')
        # beta = df/dy where f is coriolis parameter
        beta = config.getfloat('barotropic_gyre', 'beta')

        # calculate the boundary layer thickness for specified parameters
        m = (pi * 2) / np.sqrt(3) * (nu / beta) ** (1.0 / 3.0)
        # ensure the boundary layer is at least 3 gridcells wide
        logger.info(
            'Lateral boundary layer has an anticipated width of '
            f'{(m * 1e-3):03g} km'
        )
        if m <= 3.0 * resolution * 1.0e3:
            logger.warn(
                f'Resolution {resolution} km is too coarse to '
                'properly resolve the lateral boundary layer '
                f'with anticipated width of {(m * 1e-3):03g} km'
            )

        # check whether viscosity suitable for stability
        stability_parameter_max = 0.6
        dt_max = compute_max_time_step(config)
        nu_max = (
            stability_parameter_max
            * (resolution * 1.0e3) ** 2.0
            / (8 * dt_max)
        )
        if nu > nu_max:
            raise ValueError(
                f'Laplacian viscosity cannot be set to {nu}; '
                f'maximum value is {nu_max}'
            )

        dt = floor(dt_max / 3.0)
        dt_str = get_time_interval_string(seconds=dt)
        dt_btr_str = get_time_interval_string(seconds=dt / 20.0)

        nu_max = stability_parameter_max * (resolution * 1.0e3) ** 2.0 / dt
        if nu > nu_max:
            raise ValueError(
                f'Laplacian viscosity cannot be set to {nu}; '
                f'maximum value is {nu_max} or decrease the time step'
            )

        options = {'config_dt': dt_str, 'config_density0': rho_0}
        self.add_model_config_options(
            options=options, config_model='mpas-ocean'
        )

        if self.run_time_steps is not None:
            run_duration = ceil(self.run_time_steps * dt)
            stop_time_str = time.strftime(
                '0001-01-01_%H:%M:%S', time.gmtime(run_duration)
            )
            output_interval_str = time.strftime(
                '0000_%H:%M:%S', time.gmtime(run_duration)
            )
        else:
            stop_time_str = time.strftime('0004-01-01_00:00:00')
            output_interval_str = time.strftime('0000-01-00_00:00:00')

        replacements = dict(
            dt=dt_str,
            dt_btr=dt_btr_str,
            stop_time=stop_time_str,
            output_interval=output_interval_str,
            nu=f'{nu:02g}',
        )

        # make sure output is double precision
        self.add_yaml_file(
            self.package,
            self.yaml_filename,
            template_replacements=replacements,
        )


def compute_max_time_step(config):
    """
    Compute the approximate maximum time step for stability

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Config options for test case

    Returns
    -------
    dt_max : float
        The approximate maximum time step for stability
    """
    u_max = 1.0  # m/s
    stability_parameter_max = 0.25
    resolution = config.getfloat('barotropic_gyre', 'resolution')
    f_0 = config.getfloat('barotropic_gyre', 'f_0')
    dt_max = min(
        stability_parameter_max * resolution * 1e3 / (2 * u_max),
        stability_parameter_max / f_0,
    )
    return dt_max
