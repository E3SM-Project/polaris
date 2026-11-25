import os

from polaris.config import PolarisConfigParser
from polaris.e3sm.init.topo import format_lat_lon_resolution_name
from polaris.step import Step
from polaris.tasks.e3sm.init import e3sm_init
from polaris.tasks.e3sm.init.topo.antarctic_dataset import (
    add_antarctic_dataset_option,
    get_combine_step_replacements,
    replace_steps,
)
from polaris.tasks.e3sm.init.topo.combine import (
    get_combine_topo_symlinks,
    get_lat_lon_topo_steps,
)
from polaris.tasks.e3sm.init.topo.combine.files import ANTARCTIC
from polaris.tasks.e3sm.init.topo.combine.step import (
    CombineStep as TopoCombineStep,
)

from .combine import CombineStep
from .extrapolate import ExtrapolateStep
from .viz import Woa23VizStep


def get_woa23_steps(component, include_viz=False, antarctic_dataset=ANTARCTIC):
    """
    Get the shared steps for building the reusable WOA23 hydrography product.

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        The ocean component the steps belong to.

    include_viz : bool, optional
        Whether to create the :py:class:`.Woa23VizStep` and include it in the
        returned steps.  The standalone :py:class:`.Woa23` task passes
        ``include_viz=True``; other consumers that reuse the hydrography
        product as a dependency leave it ``False`` so the plots are not
        regenerated.

    antarctic_dataset : str, optional
        The Antarctic dataset whose combined topography decides where the
        hydrography is extrapolated.  Datasets other than the default have
        their own extrapolation and visualization steps.  Tasks are built
        with the default, and :py:func:`select_woa23_antarctic_dataset`
        swaps in the steps for the dataset in a user's config at setup.

    Returns
    -------
    steps : dict of {str: polaris.Step}
        All shared steps keyed by their suggested symlink names for use
        in a task.  Upstream shared combine topography steps are also included.

    config : polaris.config.PolarisConfigParser
        The shared config options for the task and its steps.
    """
    subdir = 'spherical/realistic_global/hydrography/woa23'
    config_filename = 'woa23.cfg'

    def create():
        config = PolarisConfigParser(filepath=filepath)
        config.add_from_package(
            'polaris.tasks.ocean.realistic_global.hydrography.woa23',
            config_filename,
        )
        return config

    filepath = os.path.join(component.name, subdir, config_filename)
    config = component.get_or_create_shared_config(
        filepath=filepath, create=create
    )

    topo_steps, _ = get_lat_lon_topo_steps(
        component=e3sm_init,
        resolution=0.25,
        include_viz=False,
        antarctic_dataset=antarctic_dataset,
    )
    woa23_res_name = format_lat_lon_resolution_name(0.25)
    combine_topo_name = TopoCombineStep.get_name(
        'lat_lon', woa23_res_name, antarctic_dataset
    )
    combine_topo_step = topo_steps[combine_topo_name]
    # give the steps simpler symlink names
    topo_steps = get_combine_topo_symlinks(combine_topo_step, 'combine_topo')

    combine_subdir = os.path.join(subdir, 'combine')
    combine_step = component.get_or_create_shared_step(
        step_cls=CombineStep,
        subdir=combine_subdir,
        config=config,
        config_filename=config_filename,
    )

    # the default dataset keeps the paths, and so the cached outputs, that
    # predate the choice of dataset
    if antarctic_dataset == ANTARCTIC:
        suffix = ''
    else:
        suffix = f'_{antarctic_dataset}'

    extrapolate_subdir = os.path.join(subdir, f'extrapolate{suffix}')
    extrapolate_step = component.get_or_create_shared_step(
        step_cls=ExtrapolateStep,
        subdir=extrapolate_subdir,
        config=config,
        config_filename=config_filename,
        combine_step=combine_step,
        combine_topo_step=combine_topo_step,
    )
    add_antarctic_dataset_option(extrapolate_step)

    steps: dict[str, Step] = dict(topo_steps)
    steps['woa23_combine'] = combine_step
    steps['woa23_extrapolate'] = extrapolate_step

    if include_viz:
        viz_subdir = os.path.join(subdir, f'viz{suffix}')
        viz_step = component.get_or_create_shared_step(
            step_cls=Woa23VizStep,
            subdir=viz_subdir,
            config=config,
            config_filename=config_filename,
            extrapolate_step=extrapolate_step,
            combine_topo_step=combine_topo_step,
        )
        add_antarctic_dataset_option(viz_step)

        steps['woa23_viz'] = viz_step

    return steps, config


def select_woa23_antarctic_dataset(component, steps, antarctic_dataset):
    """
    Replace the WOA23 extrapolation and visualization steps, and the combined
    topography they use, with those for an Antarctic dataset, in every task
    that has them and in the steps that refer to them.

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        The ocean component, which owns the WOA23 steps

    steps : list of polaris.Step
        The ocean steps being set up

    antarctic_dataset : str
        The Antarctic dataset, one of ``ANTARCTIC_DATASETS``
    """
    for old in steps:
        if (
            not isinstance(old, ExtrapolateStep)
            or old.combine_topo_step.antarctic_dataset == antarctic_dataset
        ):
            continue
        old_viz = [
            step
            for step in steps
            if isinstance(step, Woa23VizStep) and step.extrapolate_step is old
        ]
        new_steps, _ = get_woa23_steps(
            component=component,
            include_viz=len(old_viz) > 0,
            antarctic_dataset=antarctic_dataset,
        )
        new = new_steps['woa23_extrapolate']
        replacements: list[tuple[Step, Step]] = [(old, new)]
        replacements.extend(
            get_combine_step_replacements(
                old.combine_topo_step, new.combine_topo_step
            )
        )
        replacements.extend((viz, new_steps['woa23_viz']) for viz in old_viz)
        replace_steps(replacements, steps)
