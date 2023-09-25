from polaris import Task


class IsomipPlusTest(Task):
    """
    An ISOMIP+ test case

    Attributes
    ----------
    resolution : float
        The horizontal resolution (km) of the test case

    experiment : {'Ocean0', 'Ocean1', 'Ocean2'}
        The ISOMIP+ experiment

    vertical_coordinate : str
            The type of vertical coordinate (``z-star``, ``z-level``, etc.)

    tidal_forcing: bool
        Whether the case has tidal forcing

    time_varying_forcing : bool
        Whether the run includes time-varying land-ice forcing

    thin_film_present: bool
        Whether a thin film is present under land ice

    planar : bool, optional
        Whether the test case runs on a planar or a spherical mesh
    """

    def __init__(self, component, resdir, resolution, experiment,
                 vertical_coordinate, base_mesh, time_varying_forcing=False,
                 time_varying_load=None, thin_film_present=False,
                 tidal_forcing=False, planar=True):
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

        experiment : {'ocean0', 'ocean1', 'ocean2', 'ocean3', 'ocean4'}
            The ISOMIP+ experiment

        vertical_coordinate : str
            The type of vertical coordinate (``z-star``, ``z-level``, etc.)

        base_mesh : polaris.Step
            The shared step for creating the base mesh

        time_varying_forcing : bool, optional
            Whether the run includes time-varying land-ice forcing

        time_varying_load : {'increasing', 'decreasing', None}, optional
            Only relevant if ``time_varying_forcing = True``.  If
            ``'increasing'``, a doubling of the ice-shelf pressure will be
            applied over one year.  If ``'decreasing'``, the ice-shelf
            thickness will be reduced to zero over one year.  Otherwise,
            the default behavior is that the ice shelf grows from 10% of its
            full thickness to its full thickness over 1 year.

        thin_film_present: bool, optional
            Whether the run includes a thin film below grounded ice

        tidal_forcing: bool, optional
            Whether the run includes a single-period tidal forcing

        planar : bool, optional
            Whether the test case runs on a planar or a spherical mesh
        """
        name = experiment
        if tidal_forcing:
            name = f'tidal_forcing_{name}'
        if time_varying_forcing:
            if time_varying_load == 'increasing':
                name = f'drying_{name}'
            elif time_varying_load == 'decreasing':
                name = f'wetting_{name}'
            else:
                name = f'time_varying_{name}'
        if thin_film_present:
            name = f'thin_film_{name}'

        self.resolution = resolution
        self.experiment = experiment
        self.vertical_coordinate = vertical_coordinate
        self.time_varying_forcing = time_varying_forcing
        self.time_varying_load = time_varying_load
        self.thin_film_present = thin_film_present
        self.tidal_forcing = tidal_forcing
        self.planar = planar

        subdir = f'{resdir}/{vertical_coordinate}/{name}'
        super().__init__(component=component, name=name, subdir=subdir)

        self.add_step(base_mesh, symlink='base_mesh')

    def configure(self):
        """
        Modify the configuration options for this test case.
        """
        config = self.config
        planar = self.planar

        if not planar:
            config.add_from_package('polaris.mesh', 'mesh.cfg')
            self.config.set('spherical_mesh', 'mpas_mesh_filename',
                            'base_mesh_without_xy.nc')

        config.add_from_package('polaris.ocean.tasks.isomip_plus',
                                'isomip_plus.cfg')
