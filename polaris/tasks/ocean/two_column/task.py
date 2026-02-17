import os

from polaris import Task
from polaris.tasks.ocean.two_column.analysis import Analysis
from polaris.tasks.ocean.two_column.forward import Forward
from polaris.tasks.ocean.two_column.init import Init
from polaris.tasks.ocean.two_column.reference import Reference


class TwoColumnTask(Task):
    """
    The two-column test case tests convergence of the TEOS-10 pressure-gradient
    computation in Omega at various horizontal and vertical resolutions. The
    test uses fixed horizontal gradients in various proprties (e.g. salinity
    and pseudo-height) between two adjacent ocean columns, as set by config
    options.

    The test includes a a quasi-analytic solution to horizontal
    pressure-gradient acceleration (HPGA) used for verification. It also
    includes a set of Omega two-column initial conditions at various
    resolutions.

    The test also includes single-time-step forward model runs at each
    resolution that output Omega's version of the HPGA, and an analysis step
    that compares these runs with both the high-fidelity reference solution
    and the Python-computed HPGA from the initial conditions.
    """

    def __init__(self, component, name):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this task belongs to

        name : str
            The name of the test case, which must have a corresponding
            <name>.cfg config file in the two_column package that specifies
            which properties vary betweeen the columns.
        """
        subdir = os.path.join('two_column', name)
        super().__init__(component=component, name=name, subdir=subdir)

        self.config.add_from_package(
            'polaris.tasks.ocean.two_column', 'two_column.cfg'
        )
        self.config.add_from_package(
            'polaris.tasks.ocean.two_column',
            f'{name}.cfg',
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
        horiz_resolutions = section.getexpression('horiz_resolutions')
        vert_resolutions = section.getexpression('vert_resolutions')

        assert horiz_resolutions is not None, (
            'The "horiz_resolutions" configuration option must be set in the '
            '"two_column" section.'
        )
        assert vert_resolutions is not None, (
            'The "vert_resolutions" configuration option must be set in the '
            '"two_column" section.'
        )
        assert len(horiz_resolutions) == len(vert_resolutions), (
            'The "horiz_resolutions" and "vert_resolutions" configuration '
            'options must have the same length.'
        )

        # start fresh with no steps
        for step in list(self.steps.values()):
            self.remove_step(step)

        reference_step = Reference(component=self.component, indir=self.subdir)
        self.add_step(reference_step)

        init_steps = dict()
        forward_steps = dict()

        for horiz_res, vert_res in zip(
            horiz_resolutions, vert_resolutions, strict=True
        ):
            init_step = Init(
                component=self.component,
                horiz_res=horiz_res,
                vert_res=vert_res,
                indir=self.subdir,
            )
            self.add_step(init_step)
            init_steps[horiz_res] = init_step

        for horiz_res in horiz_resolutions:
            forward_step = Forward(
                component=self.component,
                horiz_res=horiz_res,
                indir=self.subdir,
            )
            self.add_step(forward_step)
            forward_steps[horiz_res] = forward_step

        self.add_step(
            Analysis(
                component=self.component,
                indir=self.subdir,
                dependencies={
                    'reference': reference_step,
                    'init': init_steps,
                    'forward': forward_steps,
                },
            )
        )
