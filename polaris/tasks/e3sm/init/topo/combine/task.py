import os

from polaris.task import Task
from polaris.tasks.e3sm.init.topo.combine.step import CombineStep
from polaris.tasks.e3sm.init.topo.combine.steps import get_combine_topo_steps


class CombineTask(Task):
    """
    A task for creating the combined topography dataset, used to create the
    files to be cached for use in all other contexts
    """

    def __init__(self, component, low_res):
        """
        Create a new task

        Parameters
        ----------
        component : polaris.Component
            The component the task belongs to

        low_res : bool
            Whether to use low resolution config options
        """
        antarctic_dataset = CombineStep.ANTARCTIC
        global_dataset = CombineStep.GLOBAL
        suffix = '_low_res' if low_res else ''
        name = (
            f'combine_topo_{antarctic_dataset}_{global_dataset}{suffix}_task'
        )
        subdir = os.path.join(CombineStep.get_subdir(low_res=low_res), 'task')
        super().__init__(
            component=component,
            name=name,
            subdir=subdir,
        )
        self.config.add_from_package(
            'polaris.tasks.e3sm.init.topo.combine', 'combine.cfg'
        )
        steps = get_combine_topo_steps(
            component=component,
            cached=False,
            include_viz=True,
            low_res=low_res,
        )
        for step in steps:
            self.add_step(step)
