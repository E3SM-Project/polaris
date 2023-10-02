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

    def __init__(self, component, resdir, config, resolution, experiment,
                 vertical_coordinate, planar, base_mesh, topo_map_base,
                 topo_remap_base, cull_mesh, topo_map_culled,
                 topo_remap_culled, time_varying_forcing=False,
                 time_varying_load=None, thin_film_present=False,
                 tidal_forcing=False):
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

        experiment : {'ocean0', 'ocean1', 'ocean2', 'ocean3', 'ocean4'}
            The ISOMIP+ experiment

        vertical_coordinate : str
            The type of vertical coordinate (``z-star``, ``z-level``, etc.)

        planar : bool
            Whether the test case runs on a planar or a spherical mesh

        base_mesh : polaris.Step
            The shared step for creating the base mesh

        topo_map_base : polaris.ocean.tasks.isomip_plus.topo_map.TopoMap
            The shared step for creating a topography mapping file from
            the ISOMIP+ input data to the base mesh

        topo_remap_base : polaris.ocean.tasks.isomip_plus.topo_remap.TopoRemap
            The shared step for remapping topography to the MPAS base mesh

        cull_mesh : polaris.ocean.tasks.isomip_plus.cull_mesh.CullMesh
            The shared step for culling the mesh based on the ocean mask

        topo_map_culled : polaris.ocean.tasks.isomip_plus.topo_map.TopoMap
            The shared step for creating a topography mapping file from
            the ISOMIP+ input data to the culled mesh

        topo_remap_culled : polaris.ocean.tasks.isomip_plus.topo_remap.TopoRemap
            The shared step for remapping topography to the MPAS culled mesh

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
        """  # noqa: E501
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

        self.set_shared_config(config, link='isomip_plus.cfg')

        self.add_step(base_mesh, symlink='base_mesh')
        self.add_step(topo_map_base, symlink='topo/map_base')
        self.add_step(topo_remap_base, symlink='topo/remap_base')
        self.add_step(cull_mesh, symlink='topo/cull_mesh')
        self.add_step(topo_map_culled, symlink='topo/map_culled')
        self.add_step(topo_remap_culled, symlink='topo/remap_culled')
