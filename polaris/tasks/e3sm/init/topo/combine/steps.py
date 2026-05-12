import os

from polaris.config import PolarisConfigParser
from polaris.e3sm.init.topo import format_lat_lon_resolution_name
from polaris.step import Step
from polaris.tasks.e3sm.init.topo.combine.step import CombineStep
from polaris.tasks.e3sm.init.topo.combine.viz import VizCombinedStep

_MIN_CUBED_SPHERE_RESOLUTION = 120
_MAX_LAT_LON_RESOLUTION = 1.0


def get_cubed_sphere_topo_steps(component, resolution, include_viz=False):
    """
    Get shared combined-topography steps for a cubed-sphere target grid.

    The :class:`CombineStep` (and :class:`VizCombinedStep` when requested) set
    ``default_cached = True`` in their constructors because they are expensive
    to produce.  Downstream tasks benefit from cached outputs automatically.
    Tasks that require free-running execution (e.g. standalone combine tasks)
    should add each returned step's ``subdir`` to ``self.free_running_steps``
    in their ``__init__``, as :class:`CubedSphereCombineTask` does.

    Parameters
    ----------
    component : polaris.Component
        The component that the steps will be added to.

    resolution : int
        The cubed-sphere resolution, such as 3000 or 120.

    include_viz : bool, optional
        Whether to include the visualization step or not.

    Returns
    -------
    steps : dict of str to polaris.Step
        The combine topo step and optional visualization step, keyed by step
        name.

    config : polaris.config.PolarisConfigParser
        The shared config options.
    """
    return _get_target_topo_steps(
        component=component,
        target_grid='cubed_sphere',
        resolution=resolution,
        include_viz=include_viz,
    )


def get_lat_lon_topo_steps(component, resolution, include_viz=False):
    """
    Get shared combined-topography steps for a latitude-longitude target grid.

    The :class:`CombineStep` (and :class:`VizCombinedStep` when requested) set
    ``default_cached = True`` in their constructors because they are expensive
    to produce.  Downstream tasks benefit from cached outputs automatically.
    Tasks that require free-running execution (e.g. standalone combine tasks)
    should add each returned step's ``subdir`` to ``self.free_running_steps``
    in their ``__init__``, as :class:`LatLonCombineTask` does.

    Parameters
    ----------
    component : polaris.Component
        The component that the steps will be added to.

    resolution : float
        The latitude-longitude resolution in degrees.

    include_viz : bool, optional
        Whether to include the visualization step or not.

    Returns
    -------
    steps : dict of str to polaris.Step
        The combine topo step and optional visualization step, keyed by step
        name.

    config : polaris.config.PolarisConfigParser
        The shared config options.
    """
    return _get_target_topo_steps(
        component=component,
        target_grid='lat_lon',
        resolution=resolution,
        include_viz=include_viz,
    )


def _get_target_topo_steps(component, target_grid, resolution, include_viz):
    """
    Get shared combined-topography steps for a target grid and resolution.

    Parameters
    ----------
    component : polaris.Component
        The component that the steps will be added to.

    target_grid : {'cubed_sphere', 'lat_lon'}
        The type of target grid.

    resolution : int or float
        The target resolution as a cubed-sphere face count or degrees.

    include_viz : bool
        Whether to include the visualization step or not.

    Returns
    -------
    steps : dict of str to polaris.Step
        The combine topo step and optional visualization step, keyed by step
        name.

    config : polaris.config.PolarisConfigParser
        The shared config options.
    """
    if target_grid == 'cubed_sphere':
        resolution, resolution_name = _validate_cubed_sphere_resolution(
            resolution
        )
    elif target_grid == 'lat_lon':
        resolution, resolution_name = _validate_lat_lon_resolution(resolution)
    else:
        raise ValueError(f'Unexpected target grid: {target_grid}')

    subdir = os.path.join(
        CombineStep.get_subdir(), target_grid, resolution_name
    )

    config_filename = 'combine_topo.cfg'
    filepath = os.path.join(component.name, subdir, config_filename)
    config = PolarisConfigParser(filepath=filepath)
    config.add_from_package(
        'polaris.tasks.e3sm.init.topo.combine', 'combine.cfg'
    )
    config.set('combine_topo', 'target_grid', target_grid)
    if target_grid == 'cubed_sphere':
        config.set('combine_topo', 'resolution_cubedsphere', f'{resolution}')
    else:
        config.set('combine_topo', 'resolution_latlon', f'{resolution}')

    steps: dict[str, Step] = {}
    combine_step = component.get_or_create_shared_step(
        step_cls=CombineStep,
        subdir=subdir,
        config=config,
        target_grid=target_grid,
        resolution_name=resolution_name,
    )
    combine_step._set_res_and_outputs(update=False)
    steps[combine_step.name] = combine_step

    if include_viz:
        viz_subdir = os.path.join(combine_step.subdir, 'viz')
        viz_step = component.get_or_create_shared_step(
            step_cls=VizCombinedStep,
            subdir=viz_subdir,
            config=config,
            config_filename='combine_topo.cfg',
            combine_step=combine_step,
        )
        steps[viz_step.name] = viz_step

    return steps, config


def _validate_cubed_sphere_resolution(resolution):
    """
    Validate and normalize a cubed-sphere resolution.

    Parameters
    ----------
    resolution : int or float
        The cubed-sphere resolution.

    Returns
    -------
    resolution : int
        The validated cubed-sphere resolution.

    resolution_name : str
        The corresponding resolution name.
    """
    resolution = float(resolution)
    if resolution <= 0.0:
        raise ValueError(
            f'Cubed-sphere resolution must be positive, got {resolution}.'
        )

    if not resolution.is_integer():
        raise ValueError(
            'Cubed-sphere resolution must be an integer face count, '
            f'got {resolution}.'
        )

    resolution = int(resolution)
    if resolution < _MIN_CUBED_SPHERE_RESOLUTION:
        raise ValueError(
            'Cubed-sphere resolution is implausibly coarse for combined '
            f'topography: ne{resolution}. Expected ne'
            f'{_MIN_CUBED_SPHERE_RESOLUTION} or finer.'
        )

    return resolution, f'ne{resolution}'


def _validate_lat_lon_resolution(resolution):
    """
    Validate and normalize a latitude-longitude resolution.

    Parameters
    ----------
    resolution : float
        The latitude-longitude resolution in degrees.

    Returns
    -------
    resolution : float
        The validated latitude-longitude resolution.

    resolution_name : str
        The corresponding resolution name.
    """
    resolution = float(resolution)
    if resolution <= 0.0:
        raise ValueError(
            'Latitude-longitude resolution must be positive, '
            f'got {resolution}.'
        )

    if resolution > _MAX_LAT_LON_RESOLUTION:
        raise ValueError(
            'Latitude-longitude resolution is implausibly coarse for '
            f'combined topography: {resolution} degree. Expected '
            f'{_MAX_LAT_LON_RESOLUTION} degree or finer.'
        )

    return resolution, format_lat_lon_resolution_name(resolution)
