from polaris import Task as Task
from polaris.ocean.model import omega_runs_on_gpus
from polaris.tasks.ocean.baroclinic_channel.forward import Forward as Forward
from polaris.tasks.ocean.baroclinic_channel.validate import (
    Validate as Validate,
)


class Decomp(Task):
    """
    A baroclinic channel decomposition task, which makes sure the model
    produces identical results on 4 and 8 cores, or on 1 and 2 GPUs when
    Omega runs on GPUs.
    """

    def __init__(self, component, resolution, indir, init):
        """
        Create the task

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this task belongs to

        resolution : float
            The resolution of the task in km

        indir : str
            The directory the task is in, to which ``name`` will be appended

        init : polaris.tasks.ocean.baroclinic_channel.init.Init
            A shared step for creating the initial state
        """

        super().__init__(component=component, name='decomp', indir=indir)

        self.add_step(init, symlink='init')

        self.gpu_counts = dict()
        subdirs = list()
        for procs, gpus in [(4, 1), (8, 2)]:
            name = f'{procs}proc'
            self.gpu_counts[name] = gpus

            self.add_step(
                Forward(
                    component=component,
                    init=init,
                    name=name,
                    indir=self.subdir,
                    ntasks=procs,
                    min_tasks=procs,
                    openmp_threads=1,
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

    def configure(self):
        """
        Run each step on its GPU count instead when Omega runs on GPUs
        """
        super().configure()
        if omega_runs_on_gpus(self.config, self.component):
            for name, gpus in self.gpu_counts.items():
                step = self.steps[name]
                step.ntasks = gpus
                step.min_tasks = gpus
