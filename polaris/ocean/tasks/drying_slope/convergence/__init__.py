from typing import Dict

from numpy import ceil

from polaris import Step, Task
from polaris.config import PolarisConfigParser
from polaris.ocean.resolution import resolution_to_subdir
from polaris.ocean.tasks.drying_slope.convergence.analysis import Analysis
from polaris.ocean.tasks.drying_slope.convergence.forward import Forward
from polaris.ocean.tasks.drying_slope.init import Init


class Convergence(Task):
    """
    The convergence drying_slope test case

    Attributes
    ----------
    resolutions : list of float
        The resolution of the test case in km

    damping_coeffs : list of float
        The damping coefficients at which to evaluate convergence. Must be of
        length 1.
    """

    def __init__(self, component, subdir, group_dir, config,
                 coord_type='sigma', method='ramp'):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.ocean.Ocean
            The ocean component that this task belongs to

        init : polaris.ocean.tasks.drying_slope.init.Init
            A shared step for creating the initial state

        subdir : str
            The subdirectory to put the task in

        group_dir : str
            The subdirectory to put the task group in

        config : polaris.config.PolarisConfigParser
            A shared config parser

        method: str, optional
            The wetting-and-drying method (``standard``, ``ramp``)
        coord_type : str, optional
            The type of vertical coordinate (``sigma``, ``single_layer``, etc.)

        """
        name = f'convergence_{method}'
        config_filename = 'drying_slope.cfg'
        super().__init__(component=component, name=name, subdir=subdir)

        self.damping_coeffs = []
        self.resolutions = config.getlist('drying_slope_convergence',
                                          'resolutions', dtype=float)

        analysis_dependencies: Dict[str, Dict[float, Step]] = (
            dict(mesh=dict(), init=dict(), forward=dict()))
        for resolution in self.resolutions:
            mesh_name = resolution_to_subdir(resolution)
            init_dir = f'{group_dir}/barotropic/{mesh_name}/init'
            if init_dir in component.steps:
                init_step = component.steps[init_dir]
                symlink = f'init_{mesh_name}'
            else:
                init_step = Init(component=component, resolution=resolution,
                                 name=f'init_{mesh_name}', subdir=init_dir)
                init_step.set_shared_config(config, link=config_filename)
                symlink = None
            self.add_step(init_step, symlink=symlink)

            damping_coeff = 0.01
            step_name = f'forward_{damping_coeff:03g}'
            forward_dir = f'{group_dir}/barotropic/{mesh_name}/{method}/' \
                          f'{step_name}'
            symlink = f'{step_name}_{mesh_name}'
            if forward_dir in component.steps:
                forward_step = component.steps[forward_dir]
            else:
                forward_step = Forward(component=component,
                                       name=f'{step_name}_{mesh_name}',
                                       resolution=resolution,
                                       subdir=forward_dir,
                                       init=init_step,
                                       damping_coeff=damping_coeff,
                                       coord_type=coord_type, method=method)
                forward_step.set_shared_config(config, link=config_filename)
            self.add_step(forward_step, symlink=symlink)
            analysis_dependencies['mesh'][resolution] = init_step
            analysis_dependencies['init'][resolution] = init_step
            analysis_dependencies['forward'][resolution] = forward_step

        self.add_step(Analysis(
            component=component,
            resolutions=self.resolutions,
            subdir=f'{subdir}/analysis',
            damping_coeff=damping_coeff,
            dependencies=analysis_dependencies))
