from polaris import Task
from polaris.ocean.tasks.drying_slope.forward import Forward
from polaris.ocean.tasks.drying_slope.validate import Validate


class Decomp(Task):
    """
    A drying slope decomposition task, which makes sure the model
    produces identical results on 1 and 4 cores.
    """

    def __init__(self, component, resolution, indir, init, coord_type='sigma',
                 method='ramp'):
        """
        Create the task

        Parameters
        ----------
        component : polaris.ocean.Ocean
            The ocean component that this task belongs to

        resolution : float
            The resolution of the task in km

        indir : str
            The directory the task is in, to which ``name`` will be appended

        init : polaris.ocean.tasks.drying_slope.init.Init
            A shared step for creating the initial state
        """

        super().__init__(component=component, name='decomp', indir=indir)

        self.add_step(init, symlink='init')

        subdirs = list()
        for procs in [4, 8]:
            name = f'{procs}proc'

            self.add_step(Forward(
                component=component, init=init, name=name, indir=self.subdir,
                ntasks=procs, min_tasks=procs, openmp_threads=1,
                resolution=resolution, run_time_steps=3, damping_coeff=0.001,
                coord_type=coord_type, method=method))
            subdirs.append(name)
        self.add_step(Validate(component=component, step_subdirs=subdirs,
                               indir=self.subdir))
