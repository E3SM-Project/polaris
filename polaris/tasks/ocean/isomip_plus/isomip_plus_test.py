from polaris.ocean.ice_shelf import IceShelfTask
from polaris.tasks.ocean.isomip_plus.forward import Forward
from polaris.tasks.ocean.isomip_plus.init import Init
from polaris.tasks.ocean.isomip_plus.ssh_forward import SshForward
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

    tidal_forcing: bool
        Whether the case has tidal forcing

    thin_film: bool
        Whether a thin film is present under grounded ice, as it is for
        experiments with time-varying geometry

    planar : bool, optional
        Whether the test case runs on a planar or a spherical mesh
    """

    def __init__(
        self,
        component,
        resdir,
        resolution,
        experiment,
        vertical_coordinate,
        planar,
        shared_steps,
        config,
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

        planar : bool
            Whether the test case runs on a planar or a spherical mesh

        shared_steps : dict
            The shared step for creating a topography mapping file from
            the ISOMIP+ input data to the base mesh

        config : polaris.config.PolarisConfigParser
            A config parser shared by the task and its steps, whose file is
            in the task's work directory

        tidal_forcing: bool, optional
            Whether the run includes a single-period tidal forcing
        """  # noqa: E501
        name = experiment
        if tidal_forcing:
            name = f'tidal_forcing_{name}'

        self.resolution = resolution
        self.experiment = experiment
        self.vertical_coordinate = vertical_coordinate
        self.thin_film = experiment in ['inception', 'wetting', 'drying']
        self.tidal_forcing = tidal_forcing
        self.planar = planar
        subdir = f'{resdir}/{vertical_coordinate}/{name}'
        super().__init__(
            component=component,
            min_resolution=resolution,
            name=name,
            subdir=subdir,
        )
        self.set_shared_config(config)

        for symlink, step in shared_steps.items():
            if symlink == 'topo_final':
                continue
            self.add_step(step, symlink=symlink)

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
            ForwardStep=SshForward,
            package='polaris.tasks.ocean.isomip_plus',
            yaml_filename='physics.yaml',
        )

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
            component=component, indir=subdir, init=init, forward=forward
        )
        viz.set_shared_config(config, link='isomip_plus.cfg')
        self.add_step(viz)
