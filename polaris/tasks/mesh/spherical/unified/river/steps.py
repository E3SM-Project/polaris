import os

from polaris.mesh.spherical.unified import (
    RIVER_CONFIG_FILENAME,
    get_unified_mesh_config,
)
from polaris.step import Step
from polaris.tasks.mesh.spherical.unified.coastline.steps import (
    get_unified_mesh_coastline_steps,
)
from polaris.tasks.mesh.spherical.unified.river.clip import (
    ClipRiverNetworkStep,
)
from polaris.tasks.mesh.spherical.unified.river.rasterize import (
    RasterizeRiverLatLonStep,
)
from polaris.tasks.mesh.spherical.unified.river.simplify import (
    SimplifyRiverNetworkStep,
)
from polaris.tasks.mesh.spherical.unified.river.viz import VizRiverStep


def get_unified_mesh_river_steps(
    mesh_name,
    include_viz=False,
):
    """
    Get shared river-network steps for one mesh (source, lat-lon, base-mesh).

    Parameters
    ----------
    mesh_name : str
        The name of the unified mesh

    include_viz : bool, optional
        Whether to include a visualization step

    Returns
    -------
    steps : dict of str to polaris.Step
        The river shared steps keyed by suggested subdir symlink in the task.
        The steps include shared steps from the coastline workflow;
        simplification of the source river network; rasterization of the river
        on a lat-lon grid; and clipping of the river network to the base mesh;
        and optional visualization.

    config : polaris.config.PolarisConfigParser
        The shared lat-lon river config options
    """
    component = _get_mesh_component()
    config_filename = RIVER_CONFIG_FILENAME

    config_filepath = os.path.join(
        component.name,
        'spherical',
        'unified',
        mesh_name,
        'river',
        config_filename,
    )
    config = _get_mesh_river_config(
        mesh_name=mesh_name, filepath=config_filepath
    )
    lat_lon_resolution = config.getfloat('unified_mesh', 'resolution_latlon')

    coastline_steps, _ = get_unified_mesh_coastline_steps(
        resolution=lat_lon_resolution,
        include_viz=False,
    )
    coastline_step = coastline_steps['coastline_final']

    steps: dict[str, Step] = dict(coastline_steps)
    simplify_subdir = os.path.join(
        'spherical', 'unified', mesh_name, 'river', 'simplify'
    )
    simplify_step = component.get_or_create_shared_step(
        step_cls=SimplifyRiverNetworkStep,
        subdir=simplify_subdir,
        config=config,
        config_filename=config_filename,
    )

    rasterize_subdir = os.path.join(
        'spherical', 'unified', mesh_name, 'river', 'rasterize'
    )
    rasterize_step = component.get_or_create_shared_step(
        step_cls=RasterizeRiverLatLonStep,
        subdir=rasterize_subdir,
        config=config,
        config_filename=config_filename,
        simplify_step=simplify_step,
        coastline_step=coastline_step,
    )
    steps[simplify_step.name] = simplify_step
    steps[rasterize_step.name] = rasterize_step

    clip_subdir = os.path.join(
        'spherical', 'unified', mesh_name, 'river', 'clip'
    )
    prepare_clip_step = component.get_or_create_shared_step(
        step_cls=ClipRiverNetworkStep,
        subdir=clip_subdir,
        config=config,
        config_filename=config_filename,
        simplify_step=simplify_step,
        coastline_step=coastline_step,
    )
    steps[prepare_clip_step.name] = prepare_clip_step

    if include_viz:
        viz_subdir = os.path.join(
            'spherical', 'unified', mesh_name, 'river', 'viz'
        )
        viz_step = component.get_or_create_shared_step(
            step_cls=VizRiverStep,
            subdir=viz_subdir,
            config=config,
            config_filename=config_filename,
            simplify_step=simplify_step,
            rasterize_step=rasterize_step,
        )
        steps[viz_step.name] = viz_step

    return steps, config


def _get_mesh_river_config(mesh_name, filepath):
    component = _get_mesh_component()
    if filepath in component.configs:
        return component.configs[filepath]

    return get_unified_mesh_config(mesh_name=mesh_name, filepath=filepath)


def _get_mesh_component():
    # Import lazily to avoid a circular import through polaris.tasks.mesh.
    from polaris.tasks.mesh import mesh as mesh_component

    return mesh_component
