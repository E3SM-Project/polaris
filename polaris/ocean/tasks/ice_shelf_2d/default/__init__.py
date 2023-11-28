from polaris import Task
from polaris.ocean.tasks.ice_shelf_2d.forward import Forward
from polaris.ocean.tasks.ice_shelf_2d.viz import Viz


class Default(Task):
    """
    The default ice shelf 2d test case simply creates the mesh and
    initial condition, then performs a short forward run.
    """

    def __init__(self, component, resolution, indir, shared_steps, mesh, init):
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

        shared_steps : dict of dict of polaris.Steps
            The shared steps to include as symlinks
        """
        super().__init__(component=component, name='default', indir=indir)

        for name, shared_step in shared_steps.items():
            self.add_step(shared_step, symlink=name)

        self.add_step(
            Forward(component=component, indir=self.subdir, ntasks=None,
                    min_tasks=None, openmp_threads=1, resolution=resolution,
                    mesh=mesh, init=init))

        self.add_step(
            Viz(component=component, indir=self.subdir, mesh=mesh, init=init))
