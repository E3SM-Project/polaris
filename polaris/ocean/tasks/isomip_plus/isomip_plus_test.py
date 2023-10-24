from polaris import Task


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

    def __init__(self, component, resdir, config, resolution, experiment,
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

        config : polaris.config.PolarisConfigParser
            A shared config parser

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

        self.set_shared_config(config, link='isomip_plus.cfg')

        for symlink, step in shared_steps.items():
            if symlink == 'topo_final':
                continue
            self.add_step(step, symlink=symlink)
