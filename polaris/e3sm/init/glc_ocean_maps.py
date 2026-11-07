from polaris.remap import MappingFileStep


class GlcOceanMapStep(MappingFileStep):
    """
    A step for making a conservative map between a land-ice (glc) mesh and
    an ocean mesh for E3SM's coupler.

    A map from the land ice to the ocean may smooth the land-ice geometry
    by inflating each ocean cell by :py:attr:`expand_distance` outward from
    its center before the cells are overlapped.  The map then spreads each
    land-ice cell over the ocean cells within about that distance.  pyremap
    can only inflate the cells of a mesh, so a smoothed map reads the
    ocean's MPAS mesh rather than its SCRIP file.

    The step reads its input files from ``glc_scrip.nc`` and either
    ``ocn_scrip.nc`` or, for a smoothed map, ``ocn_mesh.nc`` in its work
    directory, which the caller adds as input files.  pyremap writes the
    SCRIP files it makes to ``src_mesh.nc`` and ``dst_mesh.nc``, so those
    names are not used for inputs.

    Attributes
    ----------
    to_ocean : bool
        Whether the map is from the land ice to the ocean, rather than from
        the ocean to the land ice

    smoothed : bool
        Whether the ocean cells are inflated by :py:attr:`expand_distance`

    glc_mesh_name : str or None
        The name of the land-ice mesh, used to give the map a unique name.
        It must be set before :py:meth:`runtime_setup` is called.

    ocn_mesh_name : str or None
        The name of the ocean mesh, used to give the map a unique name.  It
        must be set before :py:meth:`runtime_setup` is called.

    expand_distance : float or None
        The distance in meters by which each ocean cell is inflated for a
        smoothed map.  It must be set to a positive value before
        :py:meth:`runtime_setup` is called.  pyremap inflates cells on the
        WGS84 ellipsoid, so on a planar mesh with a map projection, the
        distance in projected meters can differ slightly.
    """

    def __init__(
        self,
        component,
        name,
        subdir,
        to_ocean,
        smoothed=False,
        glc_mesh_name=None,
        ocn_mesh_name=None,
        expand_distance=None,
        ntasks=8,
        min_tasks=1,
        map_filename='map.nc',
    ):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        name : str
            The name of the step

        subdir : str
            The subdirectory for the step

        to_ocean : bool
            Whether the map is from the land ice to the ocean, rather than
            from the ocean to the land ice

        smoothed : bool, optional
            Whether the ocean cells are inflated by ``expand_distance``.  Only
            a map to the ocean can be smoothed.

        glc_mesh_name : str, optional
            The name of the land-ice mesh, if it is known when the step is
            created

        ocn_mesh_name : str, optional
            The name of the ocean mesh, if it is known when the step is
            created

        expand_distance : float, optional
            The distance in meters by which each ocean cell is inflated for
            a smoothed map, if it is known when the step is created

        ntasks : int, optional
            The target number of MPI tasks for the mapping tool

        min_tasks : int, optional
            The minimum number of MPI tasks for the mapping tool

        map_filename : str, optional
            The name of the map the step writes
        """
        if smoothed and not to_ocean:
            raise ValueError(
                'Only a map from the land ice to the ocean can be smoothed.'
            )
        super().__init__(
            component=component,
            name=name,
            subdir=subdir,
            ntasks=ntasks,
            min_tasks=min_tasks,
            map_filename=map_filename,
            method='conserve',
        )
        self.to_ocean = to_ocean
        self.smoothed = smoothed
        self.glc_mesh_name = glc_mesh_name
        self.ocn_mesh_name = ocn_mesh_name
        self.expand_distance = expand_distance
        self.add_output_file(filename=map_filename)

    def runtime_setup(self):
        """
        Set the source and destination grids and, for a smoothed map, how
        far the ocean cells are inflated
        """
        if self.glc_mesh_name is None or self.ocn_mesh_name is None:
            raise ValueError(
                'glc_mesh_name and ocn_mesh_name must be set before '
                'runtime_setup().'
            )
        remapper = self.remapper
        glc = dict(filename='glc_scrip.nc', mesh_name=self.glc_mesh_name)
        if self.smoothed:
            if self.expand_distance is None or self.expand_distance <= 0.0:
                raise ValueError(
                    f'A smoothed map needs a positive expand_distance, not '
                    f'{self.expand_distance}.'
                )
            # pyremap inflates the destination cells
            remapper.expand_dist = self.expand_distance
            self.src_from_scrip(**glc)
            remapper.dst_from_mpas(
                filename='ocn_mesh.nc', mesh_name=self.ocn_mesh_name
            )
        else:
            ocn = dict(filename='ocn_scrip.nc', mesh_name=self.ocn_mesh_name)
            if self.to_ocean:
                self.src_from_scrip(**glc)
                self.dst_from_scrip(**ocn)
            else:
                self.src_from_scrip(**ocn)
                self.dst_from_scrip(**glc)
        super().runtime_setup()
