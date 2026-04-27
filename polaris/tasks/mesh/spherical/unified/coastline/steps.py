import os

from polaris.config import PolarisConfigParser
from polaris.e3sm.init.topo import format_lat_lon_resolution_name
from polaris.step import Step
from polaris.tasks.mesh.spherical.unified.coastline.prepare import (
    PrepareCoastlineStep,
)
from polaris.tasks.mesh.spherical.unified.coastline.viz import (
    VizCoastlineStep,
)


def get_lat_lon_coastline_steps(
    component, combine_topo_step, resolution, include_viz=False
):
    """
    Get shared coastline-preparation steps for a lat-lon target grid.

    Parameters
    ----------
    component : polaris.Component
        The component the steps belong to

    combine_topo_step : polaris.tasks.e3sm.init.topo.combine.CombineStep
        The shared combined-topography step on the target lat-lon grid

    resolution : float
        The latitude-longitude resolution in degrees

    include_viz : bool, optional
        Whether to include a visualization step

    Returns
    -------
    steps : list of polaris.Step
        The coastline step and optional visualization step

    config : polaris.config.PolarisConfigParser
        The shared config options
    """
    resolution_name = format_lat_lon_resolution_name(resolution)
    config_filename = 'coastline.cfg'
    filepath = os.path.join(
        component.name,
        'spherical',
        'unified',
        'coastline',
        'lat_lon',
        resolution_name,
        config_filename,
    )
    config = _get_lat_lon_coastline_config(
        component=component,
        filepath=filepath,
        config_filename=config_filename,
        resolution=resolution,
    )

    steps: list[Step] = []
    subdir = os.path.join(
        'spherical',
        'unified',
        'coastline',
        'lat_lon',
        resolution_name,
        'prepare',
    )
    coastline_step = component.get_or_create_shared_step(
        step_cls=PrepareCoastlineStep,
        subdir=subdir,
        config=config,
        config_filename=config_filename,
        combine_step=combine_topo_step,
    )
    steps.append(coastline_step)

    if include_viz:
        viz_subdir = os.path.join(subdir, 'viz')
        viz_step = component.get_or_create_shared_step(
            step_cls=VizCoastlineStep,
            subdir=viz_subdir,
            config=config,
            config_filename=config_filename,
            coastline_step=coastline_step,
        )
        steps.append(viz_step)

    return steps, config


def _get_lat_lon_coastline_config(
    component, filepath, config_filename, resolution
):
    if filepath in component.configs:
        return component.configs[filepath]

    config = PolarisConfigParser(filepath=filepath)
    config.add_from_package(
        'polaris.tasks.mesh.spherical.unified.coastline',
        config_filename,
    )
    config.set('coastline', 'resolution_latlon', f'{resolution}')
    return config
