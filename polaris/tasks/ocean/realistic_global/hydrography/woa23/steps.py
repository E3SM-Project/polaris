import os

from polaris.config import PolarisConfigParser
from polaris.e3sm.init.topo import format_lat_lon_resolution_name
from polaris.step import Step
from polaris.tasks.e3sm.init import e3sm_init
from polaris.tasks.e3sm.init.topo.combine import (
    get_lat_lon_topo_steps,
)
from polaris.tasks.e3sm.init.topo.combine.step import (
    CombineStep as TopoCombineStep,
)

from .combine import CombineStep
from .extrapolate import ExtrapolateStep
from .viz import Woa23VizStep


def get_woa23_topography_step():
    """
    Get the cached combined-topography step for the WOA23 target grid.

    Returns
    -------
    combine_topo_step : polaris.tasks.e3sm.init.topo.combine.step.CombineStep
        A shared step from ``e3sm/init`` configured for the WOA23 0.25-degree
        latitude-longitude grid.
    """
    steps, _ = get_lat_lon_topo_steps(
        component=e3sm_init, resolution=0.25, include_viz=False
    )
    woa23_res_name = format_lat_lon_resolution_name(0.25)
    return steps[TopoCombineStep.get_name('lat_lon', woa23_res_name)]


def get_woa23_steps(component, combine_topo_step):
    """
    Get the shared steps for building the reusable WOA23 hydrography product.

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        The ocean component the steps belong to.

    combine_topo_step : polaris.tasks.e3sm.init.topo.combine.step.CombineStep
        The cached ``e3sm/init`` step that produces topography on the WOA23
        grid.

    Returns
    -------
    steps : dict of {str: polaris.Step}
        Shared steps for combining and extrapolating WOA23 data, keyed by
        step name.

    config : polaris.config.PolarisConfigParser
        The shared config options for the task and its steps.
    """
    subdir = 'spherical/realistic_global/hydrography/woa23'
    config_filename = 'woa23.cfg'
    config = PolarisConfigParser(
        filepath=os.path.join(component.name, subdir, config_filename)
    )
    config.add_from_package(
        'polaris.tasks.ocean.realistic_global.hydrography.woa23',
        config_filename,
    )

    combine_subdir = os.path.join(subdir, 'combine')
    combine_step = component.get_or_create_shared_step(
        step_cls=CombineStep,
        subdir=combine_subdir,
        config=config,
        config_filename=config_filename,
    )

    extrapolate_subdir = os.path.join(subdir, 'extrapolate')
    extrapolate_step = component.get_or_create_shared_step(
        step_cls=ExtrapolateStep,
        subdir=extrapolate_subdir,
        config=config,
        config_filename=config_filename,
        combine_step=combine_step,
        combine_topo_step=combine_topo_step,
    )

    viz_subdir = os.path.join(subdir, 'viz')
    viz_step = component.get_or_create_shared_step(
        step_cls=Woa23VizStep,
        subdir=viz_subdir,
        config=config,
        config_filename=config_filename,
        extrapolate_step=extrapolate_step,
        combine_topo_step=combine_topo_step,
    )

    steps: dict[str, Step] = {
        combine_step.name: combine_step,
        extrapolate_step.name: extrapolate_step,
        viz_step.name: viz_step,
    }
    return steps, config
