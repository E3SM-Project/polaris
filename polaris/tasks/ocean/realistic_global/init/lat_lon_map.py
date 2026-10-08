import os

from polaris.remap import MappingFileStep
from polaris.tasks.ocean.realistic_global.mesh_info import (
    estimate_ocean_cell_count,
)


class LatLonMapStep(MappingFileStep):
    """
    A step for building the bilinear mapping file from a global
    latitude-longitude source grid to the culled MPAS ocean mesh.

    This is the MPI (``mbtempest`` or ESMF) half of a remapping workflow; a
    serial step applies the resulting weights with ``ncremap``.  The task
    count is sized from the mesh's estimated ocean cell count and the
    ``remap_cells_per_task`` and ``remap_min_cells_per_task`` options in the
    ``[realistic_global_init]`` config section.

    Attributes
    ----------
    source_step : polaris.Step
        The upstream step that produces the source dataset.

    source_target : str
        The name of the source dataset in the work directory of
        ``source_step``.

    source_filename : str
        The name the source dataset is linked under in this step.

    source_mesh_name : str
        The name of the source grid, used to label the mapping file.

    cull_mesh_step : polaris.tasks.e3sm.init.topo.cull.cull.CullMeshStep
        The upstream cull-mesh step whose outputs describe the target MPAS
        mesh.

    mesh_name : str
        The name of the MPAS mesh, used to label the mapping file.
    """

    def __init__(
        self,
        component,
        name,
        subdir,
        source_step,
        source_target,
        source_filename,
        source_mesh_name,
        cull_mesh_step,
        mesh_name,
    ):
        """
        Create the step.

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the step belongs to.

        name : str
            The name of the step.

        subdir : str
            The subdirectory for the step.

        source_step : polaris.Step
            The step that produces the source dataset.

        source_target : str
            The name of the source dataset in the work directory of
            ``source_step``.

        source_filename : str
            The name to link the source dataset under in this step.

        source_mesh_name : str
            The name of the source grid, used to label the mapping file.

        cull_mesh_step : polaris.tasks.e3sm.init.topo.cull.cull.CullMeshStep
            The step that produces the culled ocean mesh files.

        mesh_name : str
            Name label for the MPAS mesh (used in the remapping weight
            filename).
        """
        super().__init__(
            component=component,
            name=name,
            subdir=subdir,
            ntasks=1,
            min_tasks=1,
            method='bilinear',
        )
        self.source_step = source_step
        self.source_target = source_target
        self.source_filename = source_filename
        self.source_mesh_name = source_mesh_name
        self.cull_mesh_step = cull_mesh_step
        self.mesh_name = mesh_name

    def setup(self):
        """
        Declare input files and compute ntasks from the estimated mesh size.
        """
        super().setup()
        self.add_input_file(
            filename=self.source_filename,
            work_dir_target=os.path.join(
                self.source_step.path,
                self.source_target,
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
            filename=self.source_filename,
            mesh_name=self.source_mesh_name,
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
        # the source is remapped onto the culled ocean mesh, so size from the
        # ocean-culled cell count rather than the full unified-mesh estimate
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
