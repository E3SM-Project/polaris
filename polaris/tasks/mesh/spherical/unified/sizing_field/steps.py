import os

from polaris.step import Step
from polaris.tasks.mesh.spherical.unified.river.steps import (
    get_unified_mesh_river_steps,
)
from polaris.tasks.mesh.spherical.unified.sizing_field.build import (
    BuildSizingFieldStep,
)
from polaris.tasks.mesh.spherical.unified.sizing_field.configs import (
    get_sizing_field_config,
)
from polaris.tasks.mesh.spherical.unified.sizing_field.viz import (
    VizSizingFieldStep,
)


def get_unified_mesh_sizing_field_steps(
    mesh_name,
    include_viz=False,
):
    """
    Get shared sizing-field steps for one named mesh.

    Calls the upstream step factory for river network, then creates the
    sizing-field build step.  The returned dict contains all the river-network
    shared steps plus sizing-field, and optionally visualization.

    Parameters
    ----------
    mesh_name : str
        The name of the unified mesh

    include_viz : bool, optional
        Whether to include a visualization step

    Returns
    -------
    steps : dict of str to polaris.Step
        All upstream steps plus the sizing-field build step, keyed by suggested
        subdir symlink in tasks.

    config : polaris.config.PolarisConfigParser
        The shared sizing-field config options
    """
    component = _get_mesh_component()
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
        mesh_name=mesh_name, filepath=filepath
    )

    river_steps, _ = get_unified_mesh_river_steps(
        mesh_name=mesh_name,
        include_viz=False,
    )

    coastline_step = river_steps['coastline_final']
    river_step = river_steps['river_rasterize']

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

    steps: dict[str, Step] = dict(river_steps)
    steps[build_step.name] = build_step

    if include_viz:
        viz_subdir = os.path.join(
            'spherical',
            'unified',
            mesh_name,
            'sizing_field',
            'viz',
        )
        viz_step = component.get_or_create_shared_step(
            step_cls=VizSizingFieldStep,
            subdir=viz_subdir,
            config=config,
            config_filename=config_filename,
            sizing_step=build_step,
        )
        steps[viz_step.name] = viz_step

    return steps, config


def _get_lat_lon_sizing_field_config(mesh_name, filepath):
    component = _get_mesh_component()
    if filepath in component.configs:
        return component.configs[filepath]

    return get_sizing_field_config(mesh_name=mesh_name, filepath=filepath)


def _get_mesh_component():
    # Import lazily to avoid a circular import through polaris.tasks.mesh.
    from polaris.tasks.mesh import mesh as mesh_component

    return mesh_component
