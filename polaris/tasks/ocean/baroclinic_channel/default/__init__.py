from polaris import Task as Task
from polaris.tasks.ocean.baroclinic_channel.forward import Forward as Forward
from polaris.tasks.ocean.baroclinic_channel.viz import Viz as Viz


class Default(Task):
    """
    The default baroclinic channel test case simply creates the mesh and
    initial condition, then performs a short forward run on 4 cores.
    """

    def __init__(self, component, resolution, indir, init):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this task belongs to

        resolution : float
            The resolution of the test case in km

        indir : str
            The directory the task is in, to which ``name`` will be appended

        init : polaris.tasks.ocean.baroclinic_channel.init.Init
            A shared step for creating the initial state
        """
        super().__init__(component=component, name='default', indir=indir)

        self.add_step(init, symlink='init')

        self.add_step(
            Forward(
                component=component,
                indir=self.subdir,
                ntasks=None,
                min_tasks=None,
                openmp_threads=1,
                resolution=resolution,
                run_time_steps=3,
                graph_target=f'{init.path}/culled_graph.info',
            )
        )

        self.add_step(Viz(component=component, indir=self.subdir))
