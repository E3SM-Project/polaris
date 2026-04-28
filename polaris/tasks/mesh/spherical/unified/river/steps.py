import os

from polaris.mesh.spherical.unified import (
    RIVER_CONFIG_FILENAME,
    get_unified_mesh_config,
)
from polaris.tasks.mesh.spherical.unified.river.base_mesh import (
    PrepareRiverForBaseMeshStep,
)
from polaris.tasks.mesh.spherical.unified.river.lat_lon import (
    PrepareRiverLatLonStep,
)
from polaris.tasks.mesh.spherical.unified.river.source import (
    PrepareRiverSourceStep,
)
from polaris.tasks.mesh.spherical.unified.river.viz import VizRiverStep


def get_mesh_river_source_steps(component, mesh_name):
    """
    Get shared source-level river-network steps for one mesh.
    """
    config_filename = RIVER_CONFIG_FILENAME
    filepath = os.path.join(
        component.name,
        'spherical',
        'unified',
        mesh_name,
        'river',
        'source',
        config_filename,
    )
    config = _get_mesh_river_config(
        component=component, mesh_name=mesh_name, filepath=filepath
    )

    subdir = os.path.join(
        'spherical', 'unified', mesh_name, 'river', 'source', 'prepare'
    )
    prepare_step = component.get_or_create_shared_step(
        step_cls=PrepareRiverSourceStep,
        subdir=subdir,
        config=config,
        config_filename=config_filename,
    )
    return [prepare_step], config


def get_mesh_river_lat_lon_steps(
    component,
    prepare_step,
    coastline_step,
    mesh_name,
    include_viz=False,
):
    """
    Get shared lat-lon river-network steps for one mesh.
    """
    config_filename = RIVER_CONFIG_FILENAME
    filepath = os.path.join(
        component.name,
        'spherical',
        'unified',
        mesh_name,
        'river',
        'lat_lon',
        config_filename,
    )
    config = _get_mesh_river_config(
        component=component, mesh_name=mesh_name, filepath=filepath
    )

    subdir = os.path.join(
        'spherical',
        'unified',
        mesh_name,
        'river',
        'lat_lon',
        'prepare',
    )
    prepare_lat_lon_step = component.get_or_create_shared_step(
        step_cls=PrepareRiverLatLonStep,
        subdir=subdir,
        config=config,
        config_filename=config_filename,
        prepare_step=prepare_step,
        coastline_step=coastline_step,
    )
    steps = [prepare_lat_lon_step]

    if include_viz:
        viz_subdir = os.path.join(subdir, 'viz')
        viz_step = component.get_or_create_shared_step(
            step_cls=VizRiverStep,
            subdir=viz_subdir,
            config=config,
            config_filename=config_filename,
            prepare_step=prepare_step,
            river_step=prepare_lat_lon_step,
        )
        steps.append(viz_step)

    return steps, config


def get_mesh_river_base_mesh_steps(
    component,
    prepare_step,
    coastline_step,
    mesh_name,
):
    """
    Get shared clipped river products for base-mesh consumers.
    """
    config_filename = RIVER_CONFIG_FILENAME
    filepath = os.path.join(
        component.name,
        'spherical',
        'unified',
        mesh_name,
        'river',
        'base_mesh',
        config_filename,
    )
    config = _get_mesh_river_config(
        component=component, mesh_name=mesh_name, filepath=filepath
    )

    subdir = os.path.join(
        'spherical', 'unified', mesh_name, 'river', 'base_mesh', 'prepare'
    )
    prepare_base_mesh_step = component.get_or_create_shared_step(
        step_cls=PrepareRiverForBaseMeshStep,
        subdir=subdir,
        config=config,
        config_filename=config_filename,
        prepare_step=prepare_step,
        coastline_step=coastline_step,
    )
    return [prepare_base_mesh_step], config


def _get_mesh_river_config(component, mesh_name, filepath):
    if filepath in component.configs:
        return component.configs[filepath]

    return get_unified_mesh_config(mesh_name=mesh_name, filepath=filepath)
