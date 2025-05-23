from polaris import Task as Task
from polaris.tasks.ocean.baroclinic_channel.forward import Forward as Forward
from polaris.tasks.ocean.baroclinic_channel.validate import (
    Validate as Validate,
)


class Threads(Task):
    """
    A baroclinic channel thread test case, which makes sure the model produces
    identical results with 1 and 2 threads.
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

        super().__init__(component=component, name='threads', indir=indir)

        self.add_step(init, symlink='init')

        subdirs = list()
        for openmp_threads in [1, 2]:
            name = f'{openmp_threads}thread'
            self.add_step(
                Forward(
                    component=component,
                    name=name,
                    indir=self.subdir,
                    ntasks=4,
                    min_tasks=4,
                    openmp_threads=openmp_threads,
                    resolution=resolution,
                    run_time_steps=3,
                    graph_target=f'{init.path}/culled_graph.info',
                )
            )
            subdirs.append(name)
        self.add_step(
            Validate(
                component=component, step_subdirs=subdirs, indir=self.subdir
            )
        )
