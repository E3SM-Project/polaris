from polaris import Task
from polaris.ocean.tasks.isomip_plus.init import Forcing, Init


class IsomipPlusTest(Task):
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
        Whether a thin film is present under land ice

    planar : bool, optional
        Whether the test case runs on a planar or a spherical mesh
    """

    def __init__(self, component, resdir, resolution, experiment,
                 vertical_coordinate, planar, shared_steps,
                 thin_film=False, tidal_forcing=False):
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

        thin_film: bool, optional
            Whether the run includes a thin film below grounded ice

        tidal_forcing: bool, optional
            Whether the run includes a single-period tidal forcing
        """  # noqa: E501
        name = experiment
        if tidal_forcing:
            name = f'tidal_forcing_{name}'
        if thin_film:
            name = f'thin_film_{name}'

        self.resolution = resolution
        self.experiment = experiment
        self.vertical_coordinate = vertical_coordinate
        self.thin_film = thin_film
        self.tidal_forcing = tidal_forcing
        self.planar = planar
        subdir = f'{resdir}/{vertical_coordinate}/{name}'
        super().__init__(component=component, name=name, subdir=subdir)

        for symlink, step in shared_steps.items():
            if symlink == 'topo_final':
                continue
            self.add_step(step, symlink=symlink)

        self.add_step(Init(component=component,
                           indir=subdir,
                           culled_mesh=shared_steps['topo/cull_mesh'],
                           topo=shared_steps['topo_final'],
                           experiment=experiment,
                           vertical_coordinate=vertical_coordinate,
                           thin_film=thin_film))

        self.add_step(Forcing(component=component,
                              indir=subdir,
                              culled_mesh=shared_steps['topo/cull_mesh'],
                              topo=shared_steps['topo_final'],
                              resolution=resolution,
                              experiment=experiment,
                              vertical_coordinate=vertical_coordinate,
                              thin_film=thin_film))

    def configure(self):
        """
        Modify the configuration options for this test case.
        """
        config = self.config
        config.add_from_package('polaris.ocean.ice_shelf', 'freeze.cfg')
        config.add_from_package('polaris.ocean.tasks.isomip_plus',
                                'isomip_plus.cfg')
        config.add_from_package('polaris.ocean.tasks.isomip_plus',
                                'isomip_plus_init.cfg')
        vertical_coordinate = self.vertical_coordinate
        experiment = self.experiment

        # for most coordinates, use the config options, which is 36 layers
        levels = None
        if vertical_coordinate == 'single-layer':
            levels = 1
            # this isn't a known coord_type so use z-level
            vertical_coordinate = 'z-level'

        if vertical_coordinate == 'sigma':
            if experiment in ['wetting', 'drying']:
                levels = 3
            else:
                levels = 10

        config.set('vertical_grid', 'coord_type', vertical_coordinate)
        if levels is not None:
            config.set('vertical_grid', 'vert_levels', f'{levels}')
