from polaris.ocean.ice_shelf import IceShelfTask
from polaris.tasks.ocean.isomip_plus.forward import Forward
from polaris.tasks.ocean.isomip_plus.init import Init
from polaris.tasks.ocean.isomip_plus.ssh_forward import (
    SshForward,
    ThinFilmSshForward,
)
from polaris.tasks.ocean.isomip_plus.validate import Validate
from polaris.tasks.ocean.isomip_plus.viz import Viz


class IsomipPlusTest(IceShelfTask):
    """
    An ISOMIP+ test case

    Attributes
    ----------
    resolution : float
        The horizontal resolution (km) of the test case

    experiment : str
        The ISOMIP+ experiment

    vertical_coordinate : str
            The type of vertical coordinate (``z-star``, ``z-level``, etc.)

    variant : str or None
        The variant of the default task, which adds a level to the task
        path, or None for the default task

    with_restart : bool
        Whether this is a restart test, which shares the init and SSH
        adjustment of the task it is in and checks that a run restarted
        halfway matches one that is not

    tidal_forcing: bool
        Whether the case has tidal forcing

    thin_film: bool
        Whether a thin film is present under grounded ice, as it is for
        experiments with time-varying geometry
    """

    def __init__(
        self,
        component,
        resdir,
        resolution,
        experiment,
        vertical_coordinate,
        shared_steps,
        config,
        variant=None,
        with_restart=False,
        tidal_forcing=False,
    ):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.Component
            The component the task belongs to

        resdir : str
            The subdirectory in the component for ISOMIP+ experiments of the
            given resolution

        resolution : float
            The horizontal resolution (km) of the test case

        experiment : str
            The ISOMIP+ experiment

        vertical_coordinate : str
            The type of vertical coordinate (``z-star``, ``z-level``, etc.)

        shared_steps : dict
            The shared step for creating a topography mapping file from
            the ISOMIP+ input data to the base mesh

        config : polaris.config.PolarisConfigParser
            A config parser shared by the task and its steps, whose file is
            in the task's work directory

        variant : str, optional
            The variant of the default task, which adds a level to the task
            path

        with_restart : bool, optional
            Whether this is a restart test, which shares the init and SSH
            adjustment of the task it is in and checks that a run restarted
            halfway matches one that is not.  That task must be added first.

        tidal_forcing: bool, optional
            Whether the run includes a single-period tidal forcing
        """  # noqa: E501
        name = experiment
        if tidal_forcing:
            name = f'tidal_forcing_{name}'

        self.resolution = resolution
        self.experiment = experiment
        self.vertical_coordinate = vertical_coordinate
        self.variant = variant
        self.thin_film = experiment in ['inception', 'wetting', 'drying']
        self.tidal_forcing = tidal_forcing
        self.with_restart = with_restart
        if variant is None:
            basedir = f'{resdir}/{vertical_coordinate}/{name}'
        else:
            basedir = f'{resdir}/{vertical_coordinate}/{variant}/{name}'
        if with_restart:
            name = f'{name}_with_restart'
            subdir = f'{basedir}/with_restart'
        else:
            subdir = basedir
        super().__init__(
            component=component,
            min_resolution=resolution,
            name=name,
            subdir=subdir,
            sshdir=basedir,
        )
        self.set_shared_config(config)

        for symlink, step in shared_steps.items():
            if symlink == 'topo_final':
                continue
            self.add_step(step, symlink=symlink)

        if with_restart:
            init_path = f'{basedir}/init'
            if init_path not in component.steps:
                raise ValueError(
                    f'The restart test in {subdir} needs the task in '
                    f'{basedir} to be added first.'
                )
            init = component.steps[init_path]
            self.add_step(init, symlink='init')
        else:
            init = Init(
                component=component,
                indir=subdir,
                culled_mesh=shared_steps['topo/cull_mesh'],
                topo=shared_steps['topo_final'],
                experiment=experiment,
                thin_film=self.thin_film,
            )
            init.set_shared_config(config, link='isomip_plus.cfg')
            self.add_step(init)

        ssh_adjust = self.setup_ssh_adjustment_steps(
            mesh_filename=f'{init.path}/mesh.nc',
            graph_target=f'{init.path}/culled_graph.info',
            init_filename=f'{init.path}/init.nc',
            config=config,
            config_filename='isomip_plus.cfg',
            ForwardStep=ThinFilmSshForward if self.thin_film else SshForward,
            package='polaris.tasks.ocean.isomip_plus',
            yaml_filename='physics.yaml',
        )

        if with_restart:
            self._add_restart_steps(subdir, init, ssh_adjust, config)
            return

        forward = Forward(
            component=component,
            indir=subdir,
            resolution=resolution,
            init=init,
            ssh_adjust=ssh_adjust,
            thin_film=self.thin_film,
        )
        forward.set_shared_config(config, link='isomip_plus.cfg')
        self.add_step(forward)

        viz = Viz(
            component=component,
            indir=subdir,
            init=init,
            forward=forward,
            thin_film=self.thin_film,
        )
        viz.set_shared_config(config, link='isomip_plus.cfg')
        self.add_step(viz)

    def _add_restart_steps(self, subdir, init, ssh_adjust, config):
        """
        Add a full run that writes a restart halfway, a run that restarts
        from it and a step that compares their results
        """
        steps = dict()
        for restart_test in ['full', 'restart']:
            step = Forward(
                component=self.component,
                indir=subdir,
                resolution=self.resolution,
                init=init,
                ssh_adjust=ssh_adjust,
                thin_film=self.thin_film,
                restart_test=restart_test,
            )
            step.set_shared_config(config, link='isomip_plus.cfg')
            steps[restart_test] = step
        steps['restart'].add_dependency(steps['full'], steps['full'].name)
        for step in steps.values():
            self.add_step(step)

        validate = Validate(
            component=self.component,
            step_subdirs=[steps['full'].name, steps['restart'].name],
            indir=subdir,
        )
        validate.set_shared_config(config, link='isomip_plus.cfg')
        self.add_step(validate)
