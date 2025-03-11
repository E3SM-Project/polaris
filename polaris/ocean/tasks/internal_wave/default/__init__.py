from polaris import Task as Task
from polaris.ocean.tasks.internal_wave.forward import Forward as Forward
from polaris.ocean.tasks.internal_wave.viz import Viz as Viz


class Default(Task):
    """
    The default test case for the internal wave test
    """

    def __init__(self, component, indir, init, vadv_method='standard'):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.ocean.Ocean
            The ocean component that this task belongs to

        indir : str
            The directory the task is in, to which ``name`` will be appended

        init : polaris.ocean.tasks.baroclinic_channel.init.Init
            A shared step for creating the initial state

        vadv_method : str, optional
            The vertical advection method, 'standard' or 'vlr'
        """
        super().__init__(component=component, name=f'{vadv_method}/default',
                         indir=indir)

        self.add_step(init, symlink='init')

        self.add_step(
            Forward(component=component, init=init, indir=self.subdir,
                    ntasks=None, min_tasks=None, openmp_threads=1,
                    run_time_steps=3, vadv_method=vadv_method))

        self.add_step(
            Viz(component=component, indir=self.subdir), run_by_default=False)
