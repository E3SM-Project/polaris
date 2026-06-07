from typing import Dict as Dict

from polaris import Step as Step
from polaris import Task as Task
from polaris.tasks.ocean.overflow.forward import Forward as Forward
from polaris.tasks.ocean.overflow.viz import Viz as Viz


class SmokeTest(Task):
    """
    The short overflow smoke test simply creates the mesh and
    initial condition, then performs a short forward run on 4 cores.
    """

    def __init__(self, component, indir, init, horiz_adv_order):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.ocean.Ocean
            The ocean component that this task belongs to

        indir : str
            The directory the task is in, to which ``name`` will be appended

        init : polaris.tasks.ocean.overflow.init.Init
            A shared step for creating the initial state

        horiz_adv_order : int
            The horizontal advection order for the test case
        """
        task_name = f'smoke_test_horiz_adv_order_{horiz_adv_order}'
        super().__init__(component=component, name=task_name, indir=indir)

        self.add_step(init, symlink='init')

        forward_step = Forward(
            component=component,
            init=init,
            config_section='overflow_smoke_test',
            name='forward',
            indir=self.subdir,
            horiz_adv_order=horiz_adv_order,
        )
        self.add_step(forward_step)

        viz_dependencies: Dict[str, Step] = dict(
            mesh=init, init=init, forward=forward_step
        )
        viz_step = Viz(
            component=component,
            dependencies=viz_dependencies,
            taskdir=self.subdir,
        )
        self.add_step(viz_step, run_by_default=False)
