from polaris.ocean.ice_shelf import IceShelfTask
from polaris.ocean.tasks.ice_shelf_2d.forward import Forward
from polaris.ocean.tasks.ice_shelf_2d.viz import Viz


class Default(IceShelfTask):
    """
    The default ice shelf 2d test case simply creates the mesh and
    initial condition, then performs a short forward run.

    Attributes
    ----------
    include_viz : bool
        Include Viz step
    """

    def __init__(self, component, resolution, indir, init, config,
                 include_viz=False, include_restart=False):
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

        include_viz : bool
            Include VizMap and Viz steps for each resolution
        """
        name = 'default'
        subdir = f'{indir}/default'
        if include_viz:
            name = f'{name}_with_viz'
            subdir = f'{subdir}/with_viz'
        if include_restart:
            name = f'{name}_with_restart'
            subdir = f'{subdir}/with_restart'
        # Put the ssh adjustment steps in indir rather than subdir
        super().__init__(component=component, resolution=resolution,
                         name=name, subdir=subdir, sshdir=indir)

        self.add_step(init, symlink='init')

        last_adjust_step = self._setup_ssh_adjustment_steps(
            init=init, config=config, config_filename='ice_shelf_2d.cfg',
            package='polaris.ocean.tasks.ice_shelf_2d')

        forward_path = f'{indir}/default/forward'
        if forward_path in component.steps:
            forward_step = component.steps[forward_path]
            symlink = 'forward'
        else:
            forward_step = Forward(component=component,
                                   indir=f'{indir}/default',
                                   ntasks=None, min_tasks=None,
                                   openmp_threads=1, resolution=resolution,
                                   mesh=init, init=last_adjust_step)
            forward_step.set_shared_config(config, link='ice_shelf_2d.cfg')
            symlink = None
        self.add_step(forward_step, symlink=symlink)

        if include_restart:
            restart_path = f'{indir}/default/with_restart/restart'
            if restart_path in component.steps:
                restart_step = component.steps[restart_path]
                symlink = 'restart'
            else:
                restart_step = Forward(component=component,
                                       indir=f'{indir}/default/with_restart',
                                       ntasks=None, min_tasks=None,
                                       openmp_threads=1, resolution=resolution,
                                       mesh=init, init=last_adjust_step,
                                       do_restart=True)
                symlink = None
                restart_step.set_shared_config(config, link='ice_shelf_2d.cfg')
            self.add_step(restart_step, symlink=symlink)

        if include_viz:
            self.add_step(
                Viz(component=component, indir=subdir, mesh=init,
                    init=last_adjust_step))
