import os

from polaris.remap import MappingFileStep
from polaris.tasks.ocean.realistic_global.mesh_info import (
    estimate_ocean_cell_count,
)

WOA23_EXTRAP_FILENAME = 'woa23_decav_0.25_jan_extrap.nc'


class Woa23MapStep(MappingFileStep):
    """
    A step for building the bilinear mapping file from the WOA23 0.25-degree
    latitude-longitude grid to MPAS cell centres.

    This is the MPI (``mbtempest`` or ESMF) half of the WOA23 remapping
    workflow; :py:class:`.RemapWoa23Step` applies the resulting weights.

    Attributes
    ----------
    extrapolate_step : polaris.Step
        The upstream step that produces the extrapolated WOA23 product.

    cull_mesh_step : polaris.tasks.e3sm.init.topo.cull.cull.CullMeshStep
        The upstream cull-mesh step whose outputs describe the target MPAS
        mesh.

    mesh_name : str
        The name of the MPAS mesh, used to label the mapping file.
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
            The step that produces ``woa23_decav_0.25_jan_extrap.nc``.

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
            ntasks=1,
            min_tasks=1,
            method='bilinear',
        )
        self.extrapolate_step = extrapolate_step
        self.cull_mesh_step = cull_mesh_step
        self.mesh_name = mesh_name

    def setup(self):
        """
        Declare input files and compute ntasks from the estimated mesh size.
        """
        super().setup()
        self.add_input_file(
            filename='woa23_extrap.nc',
            work_dir_target=os.path.join(
                self.extrapolate_step.path,
                WOA23_EXTRAP_FILENAME,
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
        self.remapper.src_from_lon_lat(
            filename='woa23_extrap.nc',
            mesh_name='woa23_0.25deg',
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
        # WOA23 is remapped onto the culled ocean mesh, so size from the
        # ocean-culled cell count rather than the full unified-mesh estimate.
        cell_count = estimate_ocean_cell_count(self.mesh_name, config=config)
        if cell_count is None:
            return
        section = config['realistic_global_init']
        cells_per_task = section.getint('remap_cells_per_task')
        min_cells_per_task = section.getint('remap_min_cells_per_task')
        # the floor is 1 only to keep rounding from asking for no tasks at
        # all: pyremap skips "mbpart <ntasks>" when a single task is
        # requested, so a mesh coarse enough to want one task remaps on one
        self.ntasks = max(1, round(cell_count / cells_per_task))
        self.min_tasks = max(1, round(cell_count / min_cells_per_task))
