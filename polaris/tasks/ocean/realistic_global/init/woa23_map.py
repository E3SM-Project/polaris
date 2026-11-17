from .lat_lon_map import LatLonMapStep


class Woa23MapStep(LatLonMapStep):
    """
    A step for building the bilinear mapping file from the WOA23 0.25-degree
    latitude-longitude grid to MPAS cell centers.

    This is the MPI (``mbtempest`` or ESMF) half of the WOA23 remapping
    workflow; :py:class:`.RemapWoa23Step` applies the resulting weights.
    """

    def __init__(
        self, component, subdir, extrapolate_step, cull_mesh_step, mesh_name
    ):
        """
        Create the step.

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the step belongs to.

        subdir : str
            The subdirectory for the step.

        extrapolate_step : polaris.Step
            The step that produces the extrapolated WOA23 product.

        cull_mesh_step : polaris.tasks.e3sm.init.topo.cull.cull.CullMeshStep
            The step that produces the culled ocean mesh files.

        mesh_name : str
            Name label for the MPAS mesh (used in the remapping weight
            filename).
        """
        super().__init__(
            component=component,
            name='woa23_map',
            subdir=subdir,
            source_step=extrapolate_step,
            # the filename depends on the configured month, so it is set in
            # setup()
            source_target=None,
            source_filename='woa23_extrap.nc',
            source_mesh_name='woa23_0.25deg',
            cull_mesh_step=cull_mesh_step,
            mesh_name=mesh_name,
        )

    def setup(self):
        """
        Link the extrapolated WOA23 product for the configured month.
        """
        self.source_target = self.source_step.output_filename
        super().setup()
