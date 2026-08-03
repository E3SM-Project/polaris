import os

from polaris.remap import MappingFileStep
from polaris.tasks.ocean.realistic_global.forcing.jra55.stress import (
    JRA55_STRESS_FILENAME,
)
from polaris.tasks.ocean.realistic_global.mesh_info import (
    estimate_ocean_cell_count,
)


class Jra55MapStep(MappingFileStep):
    """
    A step for building the bilinear mapping file from the JRA55-do TL319
    grid to MPAS cell centres.

    This is the MPI (``mbtempest`` or ESMF) half of the JRA55-do remapping
    workflow; :py:class:`.RemapJra55Step` applies the resulting weights.

    The method is bilinear rather than conservative because the ocean
    responds to wind stress *curl*: first-order conservative remapping gives
    a piecewise-constant stress whose curl is grid-scale noise, and pyremap's
    moab path hard-codes ``--order 1`` so second-order conservative is not
    available.

    ``map_tool`` is deliberately left at the Polaris default (``moab``).
    ESMF's default pole handling builds its pole point from the zonal average
    of the source's outermost row, which is harmless for a scalar but
    destructive for a vector in zonal/meridional components, since the local
    east/north basis rotates with longitude.  See
    ``remap_bilinear_pole_findings.md``.

    Attributes
    ----------
    stress_step : polaris.Step
        The upstream step that produces the JRA55-do wind-stress product.

    cull_mesh_step : polaris.tasks.e3sm.init.topo.cull.cull.CullMeshStep
        The upstream cull-mesh step whose outputs describe the target MPAS
        mesh.

    mesh_name : str
        The name of the MPAS mesh, used to label the mapping file.
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
        super().__init__(
            component=component,
            name='jra55_map',
            subdir=subdir,
            ntasks=1,
            min_tasks=1,
            method='bilinear',
        )
        self.stress_step = stress_step
        self.cull_mesh_step = cull_mesh_step
        self.mesh_name = mesh_name

    def setup(self):
        """
        Declare input files and compute ntasks from the estimated mesh size.
        """
        super().setup()
        self.add_input_file(
            filename=JRA55_STRESS_FILENAME,
            work_dir_target=os.path.join(
                self.stress_step.path,
                JRA55_STRESS_FILENAME,
            ),
        )
        self.add_input_file(
            filename='culled_mesh.nc',
            work_dir_target=os.path.join(
                self.cull_mesh_step.path,
                'culled_ocean_mesh.nc',
            ),
        )
        self._update_ntasks()

    def constrain_resources(self, available_resources):
        """
        Update ntasks from cell-count estimate before constraining.
        """
        self._update_ntasks()
        super().constrain_resources(available_resources)

    def run(self):
        """
        Set up the source and destination grids, then build the mapping file.
        """
        # an explicit mesh name: pyremap's automatic name is built from
        # lat[1] - lat[0], which is meaningless for a Gaussian grid
        self.remapper.src_from_lon_lat(
            filename=JRA55_STRESS_FILENAME,
            mesh_name='jra55_do_tl319',
            lon_var='lon',
            lat_var='lat',
        )
        self.remapper.dst_from_mpas(
            filename='culled_mesh.nc',
            mesh_name=self.mesh_name,
        )
        super().run()

    def _update_ntasks(self):
        """
        Set ntasks and min_tasks from the estimated mesh cell count and the
        ``remap_cells_per_task`` / ``remap_min_cells_per_task`` config
        options.  Falls back to ntasks=1 if the cell count cannot be
        estimated.
        """
        config = self.config
        cell_count = estimate_ocean_cell_count(self.mesh_name, config=config)
        if cell_count is None:
            return
        section = config['realistic_global_init']
        cells_per_task = section.getint('remap_cells_per_task')
        min_cells_per_task = section.getint('remap_min_cells_per_task')
        # the floor is 2, not 1: pyremap partitions the SCRIP files with
        # "mbpart <ntasks>", and mbpart rejects a request for a single
        # partition (see pyremap_mbpart_bug.md)
        self.ntasks = max(2, round(cell_count / cells_per_task))
        self.min_tasks = max(2, round(cell_count / min_cells_per_task))
