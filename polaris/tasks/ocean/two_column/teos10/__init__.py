import os

from polaris import Task
from polaris.tasks.ocean.two_column.init import Init
from polaris.tasks.ocean.two_column.reference import Reference


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

        self._setup_steps()

    def configure(self):
        """
        Set config options for the test case
        """
        super().configure()

        # set up the steps again in case a user has provided new resolutions
        self._setup_steps()

    def _setup_steps(self):
        """
        setup steps given resolutions
        """
        section = self.config['two_column']
        resolutions = section.getexpression('resolutions')

        # start fresh with no steps
        for step in list(self.steps.values()):
            self.remove_step(step)

        self.add_step(Reference(component=self.component, indir=self.subdir))

        for resolution in resolutions:
            self.add_step(
                Init(
                    component=self.component,
                    resolution=resolution,
                    indir=self.subdir,
                )
            )
