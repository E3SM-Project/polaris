from typing import Dict

from polaris import Step, Task
from polaris.ocean.resolution import resolution_to_subdir
from polaris.ocean.tasks.inertial_gravity_wave.analysis import Analysis
from polaris.ocean.tasks.inertial_gravity_wave.forward import Forward
from polaris.ocean.tasks.inertial_gravity_wave.init import Init
from polaris.ocean.tasks.inertial_gravity_wave.viz import Viz


def add_inertial_gravity_wave_tasks(component):
    """
    Add a task that defines a convergence test for inertial gravity waves

    component : polaris.ocean.Ocean
        the ocean component that the task will be added to
    """
    component.add_task(InertialGravityWave(component=component))


class InertialGravityWave(Task):
    """
    The convergence test case for inertial gravity waves
    """

    def __init__(self, component):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.ocean.Ocean
            The ocean component that this task belongs to
        """
        name = 'inertial_gravity_wave'
        subdir = f'planar/{name}'
        super().__init__(component=component, name=name, subdir=subdir)

        self.resolutions = [200., 100., 50., 25.]
        analysis_dependencies: Dict[str, Dict[float, Step]] = (
            dict(mesh=dict(), init=dict(), forward=dict()))
        for resolution in self.resolutions:
            mesh_name = resolution_to_subdir(resolution)
            init_step = Init(component=component, resolution=resolution,
                             taskdir=self.subdir)
            self.add_step(init_step)
            forward_step = Forward(component=component,
                                   name=f'forward_{mesh_name}',
                                   resolution=resolution,
                                   subdir=f'{self.subdir}/forward/{mesh_name}',
                                   init=init_step)
            self.add_step(forward_step)
            analysis_dependencies['mesh'][resolution] = init_step
            analysis_dependencies['init'][resolution] = init_step
            analysis_dependencies['forward'][resolution] = forward_step

        self.add_step(Analysis(component=component,
                               resolutions=self.resolutions,
                               subdir=f'{subdir}/analysis',
                               dependencies=analysis_dependencies))
        self.add_step(Viz(component=component, resolutions=self.resolutions,
                          taskdir=self.subdir),
                      run_by_default=False)

        self.config.add_from_package('polaris.ocean.convergence',
                                     'convergence.cfg')
        self.config.add_from_package(
            'polaris.ocean.tasks.inertial_gravity_wave',
            'inertial_gravity_wave.cfg')
