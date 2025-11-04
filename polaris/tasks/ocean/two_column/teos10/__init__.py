import os

from polaris import Task
from polaris.tasks.ocean.two_column.init import Init


class Teos10(Task):
    """
    The TEOS-10 two-column test case creates the mesh and initial condition,
    then computes a quasi-analytic solution to the specific volume and
    geopotential.
    """

    def __init__(self, component):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this task belongs to
        """
        name = 'teos10'
        subdir = os.path.join('two_column', name)
        super().__init__(component=component, name=name, subdir=subdir)

        self.config.add_from_package(
            'polaris.tasks.ocean.two_column', 'two_column.cfg'
        )
        self.config.add_from_package(
            'polaris.tasks.ocean.two_column.teos10', 'teos10.cfg'
        )

        self.add_step(Init(component=component, indir=self.subdir))
