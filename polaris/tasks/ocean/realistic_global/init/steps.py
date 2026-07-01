import os

from polaris.config import PolarisConfigParser
from polaris.step import Step
from polaris.tasks.e3sm.init.topo.cull.steps import get_cull_topo_steps
from polaris.tasks.ocean.realistic_global.hydrography.woa23.steps import (
    get_woa23_steps,
)

from .cull_topo import CullTopoStep
from .initial_state import InitialStateStep
from .pstar_init import RealisticPStarInitStep
from .remap_woa23 import RemapWoa23Step
from .viz import VizInitStep


def get_realistic_init_steps(component, mesh_name, include_viz=False):
    """
    Get shared steps for the realistic global ocean initialisation workflow
    for one MPAS mesh.

    Composes the full dependency chain:

    * Upstream cull-topography steps from ``e3sm/init`` (via
      :py:func:`~polaris.tasks.e3sm.init.topo.cull.steps.get_cull_topo_steps`)
    * WOA23 hydrography steps (via
      :py:func:`~polaris.tasks.ocean.realistic_global.hydrography.woa23.steps.get_woa23_steps`)
    * :py:class:`.RemapWoa23Step`
    * :py:class:`.RealisticPStarInitStep`
    * :py:class:`.InitialStateStep`

    All steps are model-independent except :py:class:`.InitialStateStep`,
    which reads ``[ocean] model`` from config at run time to select the
    appropriate output format.

    All new steps are created via
    :py:meth:`polaris.Component.get_or_create_shared_step` so that they are
    reused if the same mesh name appears in multiple tasks.

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        The ocean component the steps belong to.

    mesh_name : str
        The name of the MPAS mesh (e.g. ``'icos240km'``).

    include_viz : bool, optional
        Whether to include the (shared) :py:class:`.VizInitStep` in the
        returned steps.  The step is always created as a shared component step
        so it is part of the workflow, but it is only added to the returned
        dict (and therefore to a task's ``steps_to_run``) when this is
        ``True``.  The standalone ``RealisticGlobalInit`` task passes
        ``include_viz=True``; other consumers that reuse the init outputs as
        dependencies leave it ``False`` so the plots are not regenerated.

    Returns
    -------
    steps : dict of {str: polaris.Step}
        All steps keyed by their suggested symlink names.

    config : polaris.config.PolarisConfigParser
        Per-mesh shared config for the init steps.
    """
    cull_steps, _ = get_cull_topo_steps(mesh_name=mesh_name, include_viz=False)
    cull_mesh_step = cull_steps['cull_mesh']
    remap_topo_step = cull_steps['remap_smoothed_topo']

    woa23_steps, _ = get_woa23_steps(component=component)
    extrapolate_step = woa23_steps['woa23_extrapolate']

    base_subdir = f'spherical/realistic_global/init/{mesh_name}'
    config_filename = 'realistic_global_init.cfg'
    config = _get_init_config(component, base_subdir, config_filename)

    cull_topo_step = component.get_or_create_shared_step(
        step_cls=CullTopoStep,
        subdir=os.path.join(base_subdir, 'cull_topo'),
        config=config,
        config_filename=config_filename,
        remap_topo_step=remap_topo_step,
        cull_mesh_step=cull_mesh_step,
    )

    remap_step = component.get_or_create_shared_step(
        step_cls=RemapWoa23Step,
        subdir=os.path.join(base_subdir, 'remap_woa23'),
        config=config,
        config_filename=config_filename,
        extrapolate_step=extrapolate_step,
        cull_mesh_step=cull_mesh_step,
        mesh_name=mesh_name,
    )

    pstar_init_step = component.get_or_create_shared_step(
        step_cls=RealisticPStarInitStep,
        subdir=os.path.join(base_subdir, 'pstar_init'),
        config=config,
        config_filename=config_filename,
        remap_woa23_step=remap_step,
        cull_mesh_step=cull_mesh_step,
        cull_topo_step=cull_topo_step,
    )

    init_step = component.get_or_create_shared_step(
        step_cls=InitialStateStep,
        subdir=os.path.join(base_subdir, 'initial_state'),
        config=config,
        config_filename=config_filename,
        pstar_init_step=pstar_init_step,
        cull_mesh_step=cull_mesh_step,
    )

    viz_step = component.get_or_create_shared_step(
        step_cls=VizInitStep,
        subdir=os.path.join(base_subdir, 'viz'),
        config=config,
        config_filename=config_filename,
        init_step=init_step,
        cull_mesh_step=cull_mesh_step,
    )

    steps: dict[str, Step] = dict(cull_steps)
    steps.update(woa23_steps)
    steps[cull_topo_step.name] = cull_topo_step
    steps[remap_step.name] = remap_step
    steps[pstar_init_step.name] = pstar_init_step
    steps[init_step.name] = init_step
    if include_viz:
        steps[viz_step.name] = viz_step
    return steps, config


def _get_init_config(component, subdir, config_filename):
    """
    Get or create the shared per-mesh config for the realistic init steps.

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        The ocean component.

    subdir : str
        The subdirectory path for this mesh's init steps.

    config_filename : str
        The config filename (symlinked in each step's work directory).

    Returns
    -------
    polaris.config.PolarisConfigParser
    """
    filepath = os.path.join(component.name, subdir, config_filename)
    if filepath in component.configs:
        return component.configs[filepath]
    config = PolarisConfigParser(filepath=filepath)
    config.add_from_package(
        'polaris.tasks.ocean.realistic_global.init',
        config_filename,
    )
    return config
