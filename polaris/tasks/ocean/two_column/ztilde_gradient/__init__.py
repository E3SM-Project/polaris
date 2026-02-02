import os

from polaris import Task
from polaris.tasks.ocean.two_column.init import Init
from polaris.tasks.ocean.two_column.reference import Reference


class ZTildeGradient(Task):
    """
    The z-tilde gradient two-column test case tests convergence of the TEOS-10
    pressure-gradient computation in Omega at various horizontal resolutions.
    The test prescribes a gradient in the bottom depth of the pseudo-height
    vertical coordinate between two adjacent ocean columns, with no horizontal
    gradient in temperature or salinity.

    The test includes a a quasi-analytic solution to horizontal
    pressure-gradient acceleration (HPGA) used for verification. It also
    includes a set of Omega two-column initial conditions at various
    resolutions.

    TODO:
    Soon, the test will also include single-time-step forward model runs at
    each resolution to output Omega's version of the HPGA, followed by an
    analysis step to compute the error between Omega's HPGA and the
    quasi-analytic solution.  We will also compare Omega's HPGA with a python
    computation as part of the initial condition that is expected to match
    Omega's HPGA to high precision.
    """

    def __init__(self, component):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this task belongs to
        """
        name = 'ztilde_gradient'
        subdir = os.path.join('two_column', name)
        super().__init__(component=component, name=name, subdir=subdir)

        self.config.add_from_package(
            'polaris.tasks.ocean.two_column', 'two_column.cfg'
        )
        self.config.add_from_package(
            'polaris.tasks.ocean.two_column.ztilde_gradient',
            'ztilde_gradient.cfg',
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
