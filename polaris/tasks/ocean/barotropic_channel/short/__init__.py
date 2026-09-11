from polaris import Task as Task
from polaris.tasks.ocean.barotropic_channel.forward import Forward as Forward
from polaris.tasks.ocean.barotropic_channel.init import Init as Init
from polaris.tasks.ocean.barotropic_channel.viz import Viz as Viz


class Short(Task):
    """
    The short barotropic channel test case creates the mesh and initial
    condition, then performs a 2 hour forward run and plots the results.  It
    is too short for the wind-driven jet to spin up but long enough to catch
    a regression, so it is the variant that belongs in the Omega suites,
    where the 2 day default is too expensive.
    """

    def __init__(self, component, indir=None):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this task belongs to

        indir : str
            The directory the task is in, to which ``name`` will be appended
        """
        group_name = 'barotropic_channel'
        base_dir = f'planar/{group_name}'
        if indir is None:
            indir = base_dir
        test_name = 'short'
        super().__init__(component=component, name=test_name, indir=indir)

        init_step = Init(component=component, indir=f'{indir}/{test_name}')
        self.add_step(init_step)

        self.add_step(
            Forward(
                component=component,
                task_name=test_name,
                indir=self.subdir,
                graph_target=f'{init_step.path}/culled_graph.info',
            )
        )

        # the plots are what was broken for Omega, and they cost seconds
        self.add_step(Viz(component=component, indir=self.subdir))
