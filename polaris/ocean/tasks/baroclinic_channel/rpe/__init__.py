from polaris import Task
from polaris.ocean.tasks.baroclinic_channel.forward import Forward
from polaris.ocean.tasks.baroclinic_channel.rpe.analysis import Analysis


class Rpe(Task):
    """
    The baroclinic channel reference potential energy (RPE) test case performs
    a 20-day integration of the model forward in time at 5 different values of
    the viscosity at the given resolution.

    Attributes
    ----------
    resolution : float
        The resolution of the test case in km
    """

    def __init__(self, component, resolution, indir, init, config):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.ocean.Ocean
            The ocean component that this task belongs to

        resolution : float
            The resolution of the test case in km

        indir : str
            The directory the task is in, to which ``name`` will be appended

        init : polaris.ocean.tasks.baroclinic_channel.init.Init
            A shared step for creating the initial state

        config : polaris.config.PolarisConfigParser
            A shared config parser
        """
        super().__init__(component=component, name='rpe', indir=indir)
        self.resolution = resolution

        # this needs to be added before we can use the config options it
        # brings in to set up the steps
        self.set_shared_config(config, link='baroclinic_channel.cfg')
        self.add_step(init, symlink='init')
        self._add_rpe_and_analysis_steps()

    def configure(self):
        """
        Modify the configuration options for this test case.
        """
        super().configure()
        self._add_rpe_and_analysis_steps()

    def _add_rpe_and_analysis_steps(self):
        """ Add the steps in the test case either at init or set-up """

        config = self.config
        for step_name in list(self.steps.keys()):
            step = self.steps[step_name]
            if step_name.startswith('nu') or step_name == 'analysis':
                # remove previous RPE forward or analysis steps
                self.remove_step(step)

        component = self.component
        resolution = self.resolution

        nus = config.getlist('baroclinic_channel_rpe', 'viscosities',
                             dtype=float)
        for nu in nus:
            name = f'nu_{nu:g}'
            step = Forward(
                component=component, name=name, indir=self.subdir,
                ntasks=None, min_tasks=None, openmp_threads=1,
                resolution=resolution, nu=nu)

            step.add_yaml_file(
                'polaris.ocean.tasks.baroclinic_channel.rpe',
                'forward.yaml')
            self.add_step(step)

        self.add_step(
            Analysis(component=component, resolution=resolution, nus=nus,
                     indir=self.subdir))
