from polaris.tasks.ocean.realistic_global.forcing.jra55.stress import (
    JRA55_STRESS_FILENAME,
)

from .lat_lon_map import LatLonMapStep


class Jra55MapStep(LatLonMapStep):
    """
    A step for building the bilinear mapping file from the JRA55-do TL319
    grid to MPAS cell centers.

    This is the MPI (``mbtempest`` or ESMF) half of the JRA55-do remapping
    workflow; :py:class:`.RemapJra55Step` applies the resulting weights.

    The method is bilinear rather than conservative because the ocean
    responds to wind stress *curl*: first-order conservative remapping gives
    a piecewise-constant stress whose curl is grid-scale noise, and pyremap's
    moab path hard-codes ``--order 1`` so second-order conservative is not
    available.

    The weights are applied to the Cartesian components of the stress, which
    are scalars, so either ``map_tool`` can build them.  ESMF's default pole
    handling builds its pole point from the zonal average of the source's
    outermost row, which would cancel a vector given in zonal and meridional
    components, since the local east/north basis rotates with longitude.
    """

    def __init__(
        self, component, subdir, stress_step, cull_mesh_step, mesh_name
    ):
        """
        Create the step.

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the step belongs to.

        subdir : str
            The subdirectory for the step.

        stress_step : polaris.Step
            The step that produces the JRA55-do wind-stress product.

        cull_mesh_step : polaris.tasks.e3sm.init.topo.cull.cull.CullMeshStep
            The step that produces the culled ocean mesh files.

        mesh_name : str
            Name label for the MPAS mesh (used in the remapping weight
            filename).
        """
        # an explicit source mesh name: pyremap's automatic name is built
        # from lat[1] - lat[0], which is meaningless for a Gaussian grid
        super().__init__(
            component=component,
            name='jra55_map',
            subdir=subdir,
            source_step=stress_step,
            source_target=JRA55_STRESS_FILENAME,
            source_filename=JRA55_STRESS_FILENAME,
            source_mesh_name='jra55_do_tl319',
            cull_mesh_step=cull_mesh_step,
            mesh_name=mesh_name,
        )
