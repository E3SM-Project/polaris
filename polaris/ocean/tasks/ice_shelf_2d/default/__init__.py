from polaris.ocean.ice_shelf import IceShelfTask
from polaris.ocean.tasks.ice_shelf_2d.forward import Forward
from polaris.ocean.tasks.ice_shelf_2d.validate import Validate
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
                 include_viz=False, include_restart=False,
                 include_tides=False):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.ocean.Ocean
            The ocean component that this task belongs to

        resolution : float
            The resolution of the test case in km

        indir : str
            The directory the task is in, to which the test case name will be
            added

        include_viz : bool
            Include VizMap and Viz steps for each resolution

        include_tides: bool
            Include tidal forcing in the forward step
        """
        if include_tides and include_restart:
            raise ValueError('Restart test is not compatible with tidal '
                             'forcing')
        if include_tides:
            base_name = 'default_tidal_forcing'
        else:
            base_name = 'default'

        test_name = base_name
        test_subdir = f'{indir}/{base_name}'
        if include_viz:
            test_name = f'{base_name}_with_viz'
            test_subdir = f'{indir}/{base_name}/with_viz'
        if include_restart:
            test_name = f'{base_name}_with_restart'
            test_subdir = f'{indir}/{base_name}/with_restart'

        ssh_dir = indir
        forward_dir = f'{indir}/{base_name}'

        # Put the ssh adjustment steps in indir rather than subdir
        super().__init__(component=component, resolution=resolution,
                         name=test_name, subdir=test_subdir, sshdir=ssh_dir)

        self.add_step(init, symlink='init')

        last_adjust_step = self.setup_ssh_adjustment_steps(
            init=init, config=config, config_filename='ice_shelf_2d.cfg',
            package='polaris.ocean.tasks.ice_shelf_2d')

        forward_path = f'{forward_dir}/forward'
        if forward_path in component.steps:
            forward_step = component.steps[forward_path]
            symlink = 'forward'
        else:
            forward_step = Forward(component=component,
                                   indir=forward_dir,
                                   ntasks=None, min_tasks=None,
                                   openmp_threads=1, resolution=resolution,
                                   mesh=init, init=last_adjust_step,
                                   tidal_forcing=include_tides)
            forward_step.set_shared_config(config, link='ice_shelf_2d.cfg')
            symlink = None
        self.add_step(forward_step, symlink=symlink)

        if include_restart:
            restart_path = f'{test_subdir}/restart'
            if restart_path in component.steps:
                restart_step = component.steps[restart_path]
                symlink = 'restart'
            else:
                restart_step = Forward(component=component,
                                       indir=test_subdir,
                                       ntasks=None, min_tasks=None,
                                       openmp_threads=1, resolution=resolution,
                                       mesh=init, init=last_adjust_step,
                                       do_restart=True)
                symlink = None
                restart_step.set_shared_config(config, link='ice_shelf_2d.cfg')
                restart_step.add_dependency(forward_step, forward_step.name)
            self.add_step(restart_step, symlink=symlink)
            self.add_step(Validate(component=component,
                                   step_subdirs=['forward', 'restart'],
                                   indir=test_subdir))

        if include_viz:
            self.add_step(
                Viz(component=component, indir=test_subdir, mesh=init,
                    init=last_adjust_step))
