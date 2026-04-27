import os

from polaris.mesh.spherical.unified import (
    RIVER_CONFIG_FILENAME,
    get_unified_mesh_config,
)
from polaris.task import Task
from polaris.tasks.e3sm.init import e3sm_init
from polaris.tasks.e3sm.init.topo.combine.steps import (
    get_lat_lon_topo_steps,
)
from polaris.tasks.mesh.spherical.unified.coastline.steps import (
    get_lat_lon_coastline_steps,
)
from polaris.tasks.mesh.spherical.unified.river.steps import (
    get_mesh_river_lat_lon_steps,
    get_mesh_river_source_steps,
)


class PrepareRiverNetworkTask(Task):
    """
    A standalone task for preparing source-level river-network products.
    """

    def __init__(self, component, mesh_name):
        subdir = os.path.join(
            'spherical', 'unified', mesh_name, 'river', 'source', 'task'
        )
        super().__init__(
            component=component,
            name=f'river_network_{mesh_name}_task',
            subdir=subdir,
        )

        steps, config = get_mesh_river_source_steps(
            component=component, mesh_name=mesh_name
        )
        self.set_shared_config(config, link=RIVER_CONFIG_FILENAME)
        self.prepare_step = steps[0]
        self.add_step(self.prepare_step, symlink='prepare')


class LatLonRiverNetworkTask(Task):
    """
    A standalone task for lat-lon river masks and snapped outlet products.
    """

    def __init__(self, component, mesh_name):
        config = get_unified_mesh_config(mesh_name=mesh_name)
        resolution = config.getfloat('unified_mesh', 'resolution_latlon')
        subdir = os.path.join(
            'spherical',
            'unified',
            mesh_name,
            'river',
            'lat_lon',
            'task',
        )
        super().__init__(
            component=component,
            name=f'river_network_lat_lon_{mesh_name}_task',
            subdir=subdir,
        )

        source_steps, _ = get_mesh_river_source_steps(
            component=component, mesh_name=mesh_name
        )
        self.prepare_source_step = source_steps[0]
        self.add_step(self.prepare_source_step, symlink='prepare_source')

        combine_steps, _ = get_lat_lon_topo_steps(
            component=e3sm_init,
            resolution=resolution,
            include_viz=False,
        )
        self.combine_topo_step = combine_steps[0]
        self.add_step(self.combine_topo_step, symlink='combine_topo')

        coastline_steps, _ = get_lat_lon_coastline_steps(
            component=component,
            combine_topo_step=self.combine_topo_step,
            resolution=resolution,
            include_viz=True,
        )
        self.coastline_step = coastline_steps[0]
        self.add_step(self.coastline_step, symlink='prepare_coastline')
        self.coastline_viz_step = coastline_steps[1]
        self.add_step(
            self.coastline_viz_step,
            symlink='viz_prepare_coastline',
            run_by_default=False,
        )

        steps, config = get_mesh_river_lat_lon_steps(
            component=component,
            prepare_step=self.prepare_source_step,
            coastline_step=self.coastline_step,
            mesh_name=mesh_name,
            include_viz=True,
        )
        self.set_shared_config(config, link=RIVER_CONFIG_FILENAME)
        for step in steps:
            symlink = os.path.basename(step.subdir)
            self.add_step(step, symlink=symlink)
