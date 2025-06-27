from polaris import Task as Task

# from polaris.tasks.ocean.barotropic_channel.forward import Forward as Forward
from polaris.tasks.ocean.barotropic_channel.init import Init as Init

# from polaris.tasks.ocean.barotropic_channel.viz import Viz as Viz


class Default(Task):
    """
    The default barotropic channel test case simply creates the mesh and
    initial condition, then performs a short forward run on 4 cores.
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
        test_name = 'default'
        super().__init__(component=component, name=test_name, indir=indir)

        self.add_step(Init(component=component, indir=f'{indir}/{test_name}'))

        # self.add_step(
        #    Forward(
        #        component=component,
        #        indir=self.subdir,
        #        ntasks=None,
        #        min_tasks=None,
        #        openmp_threads=1,
        #        resolution=resolution,
        #        run_time_steps=3,
        #        graph_target=f'{init.path}/culled_graph.info',
        #    )
        # )

        # self.add_step(Viz(component=component, indir=self.subdir))
