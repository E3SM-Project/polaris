from polaris.ocean.tasks.ice_shelf_2d.forward import Forward
from polaris.ocean.tasks.ice_shelf_2d.ice_shelf import IceShelfTask
from polaris.ocean.tasks.ice_shelf_2d.viz import Viz


class Default(IceShelfTask):
    """
    The default ice shelf 2d test case simply creates the mesh and
    initial condition, then performs a short forward run.
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
        """
        super().__init__(component=component, resolution=resolution,
                         name='default', indir=indir)

        self.add_step(init, symlink='init')
        last_adjust_step = self._setup_ssh_adjustment_steps(
            init=init, config=config, config_filename='ice_shelf_2d.cfg')

        self.add_step(
            Forward(component=component, indir=self.subdir, ntasks=None,
                    min_tasks=None, openmp_threads=1, resolution=resolution,
                    mesh=init, init=last_adjust_step))

        self.add_step(
            Viz(component=component, indir=self.subdir, mesh=init,
                init=last_adjust_step))
