import os

from polaris.tasks.mesh.spherical.unified.sizing_field.build import (
    BuildSizingFieldStep,
)
from polaris.tasks.mesh.spherical.unified.sizing_field.configs import (
    get_sizing_field_config,
)
from polaris.tasks.mesh.spherical.unified.sizing_field.viz import (
    VizSizingFieldStep,
)


def get_lat_lon_sizing_field_steps(
    component,
    coastline_step,
    river_step,
    mesh_name,
    include_viz=False,
):
    """
    Get shared sizing-field steps for one named mesh.
    """
    config_filename = 'sizing_field.cfg'
    filepath = os.path.join(
        component.name,
        'spherical',
        'unified',
        mesh_name,
        'sizing_field',
        config_filename,
    )
    config = _get_lat_lon_sizing_field_config(
        component=component, mesh_name=mesh_name, filepath=filepath
    )

    subdir = os.path.join(
        'spherical',
        'unified',
        mesh_name,
        'sizing_field',
        'build',
    )
    build_step = component.get_or_create_shared_step(
        step_cls=BuildSizingFieldStep,
        subdir=subdir,
        config=config,
        config_filename=config_filename,
        coastline_step=coastline_step,
        river_step=river_step,
    )
    steps = [build_step]

    if include_viz:
        viz_subdir = os.path.join(subdir, 'viz')
        viz_step = component.get_or_create_shared_step(
            step_cls=VizSizingFieldStep,
            subdir=viz_subdir,
            config=config,
            config_filename=config_filename,
            sizing_step=build_step,
        )
        steps.append(viz_step)

    return steps, config


def _get_lat_lon_sizing_field_config(component, mesh_name, filepath):
    if filepath in component.configs:
        return component.configs[filepath]

    return get_sizing_field_config(mesh_name=mesh_name, filepath=filepath)
