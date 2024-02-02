from typing import Dict

from numpy import ceil

from polaris import Step, Task
from polaris.ocean.resolution import resolution_to_subdir
from polaris.ocean.tasks.drying_slope.convergence.analysis import Analysis
from polaris.ocean.tasks.drying_slope.convergence.forward import Forward
from polaris.ocean.tasks.drying_slope.init import Init

# from polaris.ocean.tasks.drying_slope.viz import Viz


class Convergence(Task):
    """
    The convergence drying_slope test case

    Attributes
    ----------
    resolution : float
        The resolution of the test case in km

    coord_type : str
        The type of vertical coordinate (``sigma``, ``single_layer``, etc.)

    damping_coeffs: list of float
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

        method: str
            The wetting-and-drying method (``standard``, ``ramp``)
        """
        name = f'convergence_{method}'
        super().__init__(component=component, name=name, subdir=subdir)

        config_filename = 'drying.cfg'
        self.damping_coeffs = []
        self.resolutions = [0.25, 0.5, 1, 2]
        # self.resolutions = self.config.getlist('drying_slope_convergence',
        #                                        'resolutions')

        analysis_dependencies: Dict[str, Dict[float, Step]] = (
            dict(mesh=dict(), init=dict(), forward=dict()))
        for resolution in self.resolutions:
            mesh_name = resolution_to_subdir(resolution)
            init_dir = f'{group_dir}/barotropic/{mesh_name}/init'
            symlink = f'init_{mesh_name}'
            if init_dir in component.steps:
                init_step = component.steps[init_dir]
            else:
                init_step = Init(component=component, resolution=resolution,
                                 name=f'init_{mesh_name}', subdir=init_dir)
                init_step.set_shared_config(config, link=config_filename)
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
        # self.add_step(Viz(component=component, resolutions=self.resolutions,
        #                   taskdir=self.subdir),
        #               run_by_default=False)
