import os

from polaris.mesh.spherical.unified import get_unified_mesh_config
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
from polaris.tasks.mesh.spherical.unified.sizing_field.steps import (
    get_lat_lon_sizing_field_steps,
)


class SizingFieldTask(Task):
    """
    A standalone task for building one named unified sizing field.
    """

    def __init__(self, component, mesh_name):
        config = get_unified_mesh_config(mesh_name=mesh_name)
        resolution = config.getfloat('unified_mesh', 'resolution_latlon')
        subdir = os.path.join(
            'spherical',
            'unified',
            mesh_name,
            'sizing_field',
            'task',
        )
        super().__init__(
            component=component,
            name=f'sizing_field_{mesh_name}_task',
            subdir=subdir,
        )

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

        source_steps, _ = get_mesh_river_source_steps(
            component=component, mesh_name=mesh_name
        )
        self.prepare_source_step = source_steps[0]
        self.add_step(self.prepare_source_step, symlink='prepare_river_source')

        river_steps, _ = get_mesh_river_lat_lon_steps(
            component=component,
            prepare_step=self.prepare_source_step,
            coastline_step=self.coastline_step,
            mesh_name=mesh_name,
            include_viz=False,
        )
        self.river_step = river_steps[0]
        self.add_step(self.river_step, symlink='prepare_river_lat_lon')

        sizing_steps, config = get_lat_lon_sizing_field_steps(
            component=component,
            coastline_step=self.coastline_step,
            river_step=self.river_step,
            mesh_name=mesh_name,
            include_viz=True,
        )
        self.set_shared_config(config, link='sizing_field.cfg')
        for step in sizing_steps:
            symlink = os.path.basename(step.subdir)
            self.add_step(step, symlink=symlink)
