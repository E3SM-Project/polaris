from polaris import Task as Task
from polaris.tasks.ocean.internal_wave.forward import Forward as Forward
from polaris.tasks.ocean.internal_wave.rpe.analysis import Analysis as Analysis


class Rpe(Task):
    """
    The internal wave reference potential energy (RPE) test case performs
    a 20-day integration of the model forward in time at 5 different values of
    the viscosity at the given resolution.

    Attributes
    ----------
    resolution : float
        The resolution of the test case in km

    init : polaris.tasks.ocean.baroclinic_channel.init.Init
        A shared step for creating the initial state
    """

    def __init__(self, component, indir, init, config, vadv_method='standard'):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.ocean.Ocean
            The ocean component that this task belongs to

        indir : str
            The directory the task is in, to which ``name`` will be appended

        init : polaris.tasks.ocean.baroclinic_channel.init.Init
            A shared step for creating the initial state

        config : polaris.config.PolarisConfigParser
            A shared config parser

        vadv_method : str, optional
            The vertical advection method, 'standard' or 'vlr'
        """
        self.vadv_method = vadv_method
        super().__init__(
            component=component, name=f'{vadv_method}/rpe', indir=indir
        )

        # this needs to be added before we can use the config options it
        # brings in to set up the steps
        self.set_shared_config(config, link='internal_wave.cfg')
        self.add_step(init, symlink='init')
        self.init = init
        self._add_rpe_and_analysis_steps()

    def configure(self):
        """
        Modify the configuration options for this test case.
        """
        super().configure()
        self._add_rpe_and_analysis_steps()

    def _add_rpe_and_analysis_steps(self):
        """Add the steps in the test case either at init or set-up"""

        config = self.config
        for step_name in list(self.steps.keys()):
            step = self.steps[step_name]
            if step_name.startswith('nu') or step_name == 'analysis':
                # remove previous RPE forward or analysis steps
                self.remove_step(step)

        component = self.component

        nus = config.getlist('internal_wave_rpe', 'viscosities', dtype=float)
        for nu in nus:
            name = f'nu_{nu:g}'
            step = Forward(
                component=component,
                name=name,
                init=self.init,
                indir=self.subdir,
                ntasks=None,
                min_tasks=None,
                openmp_threads=1,
                nu=nu,
                vadv_method=self.vadv_method,
            )

            step.add_yaml_file(
                'polaris.tasks.ocean.internal_wave.rpe', 'forward.yaml'
            )
            self.add_step(step)

        self.add_step(
            Analysis(component=component, nus=nus, indir=self.subdir)
        )
