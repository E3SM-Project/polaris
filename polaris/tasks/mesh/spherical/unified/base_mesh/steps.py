import os

from polaris.mesh.spherical.unified import get_unified_mesh_config
from polaris.mesh.spherical.unified.base_mesh import (
    UnifiedBaseMeshStep,
)
from polaris.tasks.mesh.spherical.unified.base_mesh.viz import VizBaseMeshStep
from polaris.tasks.mesh.spherical.unified.sizing_field.steps import (
    get_unified_mesh_sizing_field_steps,
)


def get_unified_base_mesh_config(mesh_name, filepath=None):
    """
    Load one unified mesh config with spherical-mesh and viz defaults.

    mesh_name : str
        The name of the unified mesh.

    filepath : str, optional
        The config filepath relative to the component's work directory.
        If the config is already registered under this path it is returned
        unchanged.

    Returns
    -------
    config : polaris.config.PolarisConfigParser
        The shared config options for the named unified base mesh.
    """
    component = _get_mesh_component()
    if filepath in component.configs:
        return component.configs[filepath]

    config = get_unified_mesh_config(mesh_name=mesh_name, filepath=filepath)
    config.add_from_package(
        'polaris.tasks.mesh.spherical.unified.base_mesh', 'base_mesh.cfg'
    )

    min_cell_width, max_cell_width = _get_mesh_cell_width_bounds(config)
    config.set('spherical_mesh', 'prefix', 'UN')
    config.set('spherical_mesh', 'min_cell_width', f'{min_cell_width:g}')
    config.set('spherical_mesh', 'max_cell_width', f'{max_cell_width:g}')
    return config


def get_unified_base_mesh_steps(mesh_name, include_viz=False):
    """
    Get shared steps for building one named unified base mesh.

    Calls the upstream step factories for combined topography, coastline,
    river network, and sizing field, then creates the base-mesh build step.
    All upstream factories return dicts keyed by step name; the returned
    dict preserves insertion order: combine-topo, coastline, river-source,
    river-lat-lon, river-base-mesh, sizing-field, base-mesh build, and
    optionally visualization.

    Parameters
    ----------
    mesh_name : str
        The name of the unified mesh.

    include_viz : bool, optional
        Whether to include the visualization step.

    Returns
    -------
    steps : dict of str to polaris.Step
        All steps needed to build the base mesh, keyed by step name.

    config : polaris.config.PolarisConfigParser
        The shared config options for the named unified base mesh.
    """
    component = _get_mesh_component()
    config_filename = 'base_mesh.cfg'
    filepath = os.path.join(
        component.name,
        'spherical',
        'unified',
        mesh_name,
        'base_mesh',
        config_filename,
    )
    config = get_unified_base_mesh_config(
        mesh_name=mesh_name, filepath=filepath
    )

    sizing_steps, _ = get_unified_mesh_sizing_field_steps(
        mesh_name=mesh_name,
        include_viz=False,
    )
    river_clip_step = sizing_steps['river_clip']
    sizing_step = sizing_steps['sizing_field']

    subdir = os.path.join(
        'spherical', 'unified', mesh_name, 'base_mesh', 'build'
    )
    build_step = component.get_or_create_shared_step(
        step_cls=UnifiedBaseMeshStep,
        subdir=subdir,
        config=config,
        config_filename=config_filename,
        sizing_field_step=sizing_step,
        river_clip_step=river_clip_step,
        mesh_name=mesh_name,
    )

    steps = dict(sizing_steps)
    steps[build_step.name] = build_step

    if include_viz:
        viz_subdir = os.path.join(
            'spherical', 'unified', mesh_name, 'base_mesh', 'viz'
        )
        viz_step = component.get_or_create_shared_step(
            step_cls=VizBaseMeshStep,
            subdir=viz_subdir,
            config=config,
            config_filename=config_filename,
            base_mesh_step=build_step,
            sizing_step=sizing_step,
            river_clip_step=river_clip_step,
        )
        steps[viz_step.name] = viz_step

    return steps, config


def _get_mesh_component():
    # Import lazily to avoid a circular import through polaris.tasks.mesh.
    from polaris.tasks.mesh import mesh as mesh_component

    return mesh_component


def _get_mesh_cell_width_bounds(config):
    """
    Get representative min and max cell widths from unified mesh settings.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        The unified mesh config containing a ``sizing_field`` section with
        background and optional refinement cell-width options.

    Returns
    -------
    min_width : float
        The minimum cell width in km across all active sizing-field options.

    max_width : float
        The maximum cell width in km across all active sizing-field options.
    """
    section = config['sizing_field']
    widths = [
        section.getfloat('ocean_background_min_km'),
        section.getfloat('ocean_background_max_km'),
        section.getfloat('land_background_km'),
    ]

    if section.getboolean('enable_river_channel_refinement', fallback=True):
        widths.append(section.getfloat('river_channel_km'))

    widths = [width for width in widths if width is not None]
    return min(widths), max(widths)
