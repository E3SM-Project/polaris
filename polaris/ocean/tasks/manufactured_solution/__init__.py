from typing import Dict

from polaris import Step, Task
from polaris.ocean.resolution import resolution_to_subdir
from polaris.ocean.tasks.manufactured_solution.analysis import Analysis
from polaris.ocean.tasks.manufactured_solution.forward import Forward
from polaris.ocean.tasks.manufactured_solution.init import Init
from polaris.ocean.tasks.manufactured_solution.viz import Viz


def add_manufactured_solution_tasks(component):
    """
    Add a task that defines a convergence test that uses the method of
    manufactured solutions

    component : polaris.ocean.Ocean
        the ocean component that the task will be added to
    """
    component.add_task(ManufacturedSolution(component=component))
    component.add_task(ManufacturedSolution(component=component, del2=True))
    component.add_task(ManufacturedSolution(component=component, del4=True))


class ManufacturedSolution(Task):
    """
    The convergence test case using the method of manufactured solutions

    Attributes
    ----------
    resolutions : list of floats
        The resolutions of the test case in km
    """
    def __init__(self, component, del2=False, del4=False):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.ocean.Ocean
            The ocean component that this task belongs to

        del2 : bool
            Whether to evaluate the momentum del2 operator

        del4 : bool
            Whether to evaluate the momentum del4 operator
        """
        name = 'manufactured_solution'
        taskdir = f'planar/{name}'
        if del2:
            name = f'{name}_del2'
            subdir = f'{taskdir}/del2'
        elif del4:
            name = f'{name}_del4'
            subdir = f'{taskdir}/del4'
        else:
            subdir = f'{taskdir}/default'

        super().__init__(component=component, name=name, subdir=subdir)

        max_resolution = 200.
        self.resolutions = [max_resolution,
                            max_resolution / 2,
                            max_resolution / 4,
                            max_resolution / 8]
        analysis_dependencies: Dict[str, Dict[float, Step]] = (
            dict(mesh=dict(), init=dict(), forward=dict()))
        for resolution in self.resolutions:
            mesh_name = resolution_to_subdir(resolution)

            init_name = f'init_{mesh_name}'
            init_subdir = f'{taskdir}/init/{mesh_name}'
            if init_subdir in component.steps:
                init_step = component.steps[init_subdir]
            else:
                init_step = Init(component=component, resolution=resolution,
                                 subdir=init_subdir, name=init_name)
            self.add_step(init_step, symlink='init/{mesh_name}')

            forward_name = f'forward_{mesh_name}'
            if del2:
                forward_name = f'{forward_name}_del2'
            if del4:
                forward_name = f'{forward_name}_del4'
            forward_step = Forward(component=component, resolution=resolution,
                                   name=forward_name,
                                   subdir=f'{self.subdir}/forward/{mesh_name}',
                                   init=init_step, del2=del2, del4=del4)
            self.add_step(forward_step)

            analysis_dependencies['mesh'][resolution] = init_step
            analysis_dependencies['init'][resolution] = init_step
            analysis_dependencies['forward'][resolution] = forward_step

        self.add_step(Analysis(component=component,
                               resolutions=self.resolutions,
                               subdir=f'{self.subdir}/analysis',
                               dependencies=analysis_dependencies))
        self.add_step(Viz(component=component, resolutions=self.resolutions,
                          taskdir=self.subdir),
                      run_by_default=False)

        self.config.add_from_package('polaris.ocean.convergence',
                                     'convergence.cfg')
        self.config.add_from_package(
            'polaris.ocean.tasks.manufactured_solution',
            'manufactured_solution.cfg')

    def configure(self):
        """
        Set omega default config options
        """
        super().configure()
        config = self.config
        model = config.get('ocean', 'model')
        if model == 'omega':
            config.set('convergence_forward', 'time_integrator', 'RungeKutta4')
