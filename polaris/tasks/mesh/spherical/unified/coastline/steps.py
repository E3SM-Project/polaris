import os
from typing import TypeAlias, Union

from polaris.config import PolarisConfigParser
from polaris.e3sm.init.topo import format_lat_lon_resolution_name
from polaris.mesh.spherical.unified.resolutions import FINEST_RESOLUTION
from polaris.step import Step
from polaris.tasks.e3sm.init import e3sm_init
from polaris.tasks.e3sm.init.topo.combine.step import CombineStep
from polaris.tasks.e3sm.init.topo.combine.steps import (
    get_lat_lon_topo_steps,
)
from polaris.tasks.mesh.spherical.unified.coastline.compute import (
    ComputeCoastlineStep,
)
from polaris.tasks.mesh.spherical.unified.coastline.remap import (
    RemapCoastlineStep,
)
from polaris.tasks.mesh.spherical.unified.coastline.viz import (
    VizCoastlineStep,
)

CoastlineStep: TypeAlias = Union[ComputeCoastlineStep, RemapCoastlineStep]


def get_unified_mesh_coastline_steps(
    resolution,
    include_viz=False,
):
    """
    Get shared coastline-preparation steps for a lat-lon target grid.

    A :class:`ComputeCoastlineStep` is always created at the finest supported
    resolution using the finest combined-topography step.

    For coarser resolutions, a :class:`RemapCoastlineStep` is also created to
    remap the finest-resolution coastline to the requested resolution.

    Parameters
    ----------
    resolution : float
        The latitude-longitude resolution in degrees for this grid

    include_viz : bool, optional
        Whether to include a visualization step

    Returns
    -------
    steps : dict of str to polaris.Step
        The coastline steps keyed by suggested subdir symlink in the task.
        Contains ``'coastline_compute'`` at resolutions other than the finest;
        contains ``'coastline_final'`` with the coastline output for downstream
        workflows; contains ``'coastline_viz'`` when ``include_viz=True``.

    config : polaris.config.PolarisConfigParser
        The shared config options
    """
    component = _get_mesh_component()
    fine_resolution_name = format_lat_lon_resolution_name(FINEST_RESOLUTION)
    resolution_name = format_lat_lon_resolution_name(resolution)

    config_filename = 'coastline.cfg'
    filepath = os.path.join(
        component.name,
        'spherical',
        'unified',
        'coastline',
        config_filename,
    )
    config = _get_lat_lon_coastline_config(
        filepath=filepath,
        config_filename=config_filename,
    )

    # ComputeCoastlineStep always uses the finest-resolution combined topo
    fine_combine_steps, _ = get_lat_lon_topo_steps(
        component=e3sm_init,
        resolution=FINEST_RESOLUTION,
        include_viz=False,
    )
    fine_combine_step_name = CombineStep.get_name(
        target_grid='lat_lon', resolution_name=fine_resolution_name
    )
    fine_combine_step = fine_combine_steps[fine_combine_step_name]

    steps: dict[str, Step] = {
        f'combine_topo_lat_lon_{fine_resolution_name}': fine_combine_step
    }

    prepare_subdir = os.path.join(
        'spherical',
        'unified',
        'coastline',
        fine_resolution_name,
        'compute',
    )
    compute_step = component.get_or_create_shared_step(
        step_cls=ComputeCoastlineStep,
        subdir=prepare_subdir,
        config=config,
        config_filename=config_filename,
        combine_step=fine_combine_step,
    )

    is_finest = resolution == FINEST_RESOLUTION

    if is_finest:
        steps['coastline_final'] = compute_step
    else:
        steps['coastline_compute'] = compute_step

        remap_subdir = os.path.join(
            'spherical',
            'unified',
            'coastline',
            resolution_name,
            'remap',
        )
        remap_step = component.get_or_create_shared_step(
            step_cls=RemapCoastlineStep,
            subdir=remap_subdir,
            config=config,
            config_filename=config_filename,
            fine_coastline_step=compute_step,
            coarse_resolution=resolution,
        )
        steps['coastline_final'] = remap_step

    if include_viz:
        viz_subdir = os.path.join(
            'spherical',
            'unified',
            'coastline',
            resolution_name,
            'viz',
        )
        viz_step = component.get_or_create_shared_step(
            step_cls=VizCoastlineStep,
            subdir=viz_subdir,
            config=config,
            config_filename=config_filename,
            coastline_step=steps['coastline_final'],
        )
        steps['viz_coastline'] = viz_step

    return steps, config


def _get_lat_lon_coastline_config(filepath, config_filename):
    component = _get_mesh_component()
    if filepath in component.configs:
        return component.configs[filepath]

    config = PolarisConfigParser(filepath=filepath)
    config.add_from_package(
        'polaris.tasks.mesh.spherical.unified.coastline',
        config_filename,
    )
    return config


def _get_mesh_component():
    # Import lazily to avoid a circular import through polaris.tasks.mesh.
    from polaris.tasks.mesh import mesh as mesh_component

    return mesh_component
