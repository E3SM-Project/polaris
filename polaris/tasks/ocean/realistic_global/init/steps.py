import os

from polaris.config import PolarisConfigParser
from polaris.step import Step
from polaris.tasks.e3sm.init.topo.cull.steps import get_cull_topo_steps
from polaris.tasks.ocean.realistic_global.forcing.jra55.steps import (
    get_jra55_steps,
)
from polaris.tasks.ocean.realistic_global.hydrography.woa23.steps import (
    get_woa23_steps,
)
from polaris.tasks.ocean.realistic_global.mesh_configs import (
    add_realistic_global_mesh_config,
)
from polaris.tasks.ocean.realistic_global.models import (
    DEFAULT_MODEL,
    model_subdir,
)

from .cull_topo import CullTopoStep
from .forcing import ForcingStep
from .initial_state import InitialStateStep
from .jra55_map import Jra55MapStep
from .pstar_init import RealisticPStarInitStep
from .remap_jra55 import RemapJra55Step
from .remap_woa23 import RemapWoa23Step
from .viz import VizInitStep
from .woa23_map import Woa23MapStep

CONFIG_FILENAME = 'init.cfg'


def get_realistic_init_steps(
    component, mesh_name, include_viz=False, model=DEFAULT_MODEL
):
    """
    Get shared steps for the realistic global ocean initialization workflow
    for one MPAS mesh.

    Composes the full dependency chain:

    * Upstream cull-topography steps from ``e3sm/init`` (via
      :py:func:`~polaris.tasks.e3sm.init.topo.cull.steps.get_cull_topo_steps`)
    * WOA23 hydrography steps (via
      :py:func:`~polaris.tasks.ocean.realistic_global.hydrography.woa23.steps.get_woa23_steps`)
    * JRA55-do wind-stress steps (via
      :py:func:`~polaris.tasks.ocean.realistic_global.forcing.jra55.steps.get_jra55_steps`)
    * :py:class:`.CullTopoStep`
    * :py:class:`.Woa23MapStep`
    * :py:class:`.RemapWoa23Step`
    * :py:class:`.Jra55MapStep`
    * :py:class:`.RemapJra55Step`
    * :py:class:`.RealisticPStarInitStep`
    * :py:class:`.InitialStateStep`
    * :py:class:`.ForcingStep`
    * :py:class:`.VizInitStep`, only if ``include_viz`` is ``True``

    :py:class:`.InitialStateStep`, :py:class:`.ForcingStep` and
    :py:class:`.VizInitStep` write or read files in one model's format, so
    they are model-dependent: they live under ``init/<model>/`` with a copy of
    ``init.cfg`` of their own, and their ``[ocean] model`` must be ``model``.
    The other steps are model-neutral and are shared by both models' chains.
    See :py:mod:`polaris.tasks.ocean.realistic_global.models`.

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

    model : str, optional
        The ocean model to build the model-dependent steps for.

    Returns
    -------
    steps : dict of {str: polaris.Step}
        All steps keyed by their suggested symlink names.

    config : polaris.config.PolarisConfigParser
        Per-mesh shared config for the model-neutral init steps.
    """
    cull_steps, _ = get_cull_topo_steps(mesh_name=mesh_name, include_viz=False)
    cull_mesh_step = cull_steps['cull_mesh']
    remap_topo_step = cull_steps['remap_smoothed_topo']

    woa23_steps, _ = get_woa23_steps(component=component)
    extrapolate_step = woa23_steps['woa23_extrapolate']

    jra55_steps, _ = get_jra55_steps(component=component)
    stress_step = jra55_steps['jra55_stress']

    base_subdir = init_subdir(mesh_name)
    config_filename = CONFIG_FILENAME
    config = _get_init_config(
        component, base_subdir, config_filename, mesh_name
    )
    model_dir = model_subdir(base_subdir, model)
    model_config = _get_init_config(
        component, model_dir, config_filename, mesh_name
    )

    cull_topo_step = component.get_or_create_shared_step(
        step_cls=CullTopoStep,
        subdir=os.path.join(base_subdir, 'cull_topo'),
        config=config,
        config_filename=config_filename,
        remap_topo_step=remap_topo_step,
        cull_mesh_step=cull_mesh_step,
    )

    woa23_map_step = component.get_or_create_shared_step(
        step_cls=Woa23MapStep,
        subdir=os.path.join(base_subdir, 'woa23_map'),
        config=config,
        config_filename=config_filename,
        extrapolate_step=extrapolate_step,
        cull_mesh_step=cull_mesh_step,
        mesh_name=mesh_name,
    )

    remap_step = component.get_or_create_shared_step(
        step_cls=RemapWoa23Step,
        subdir=os.path.join(base_subdir, 'remap_woa23'),
        config=config,
        config_filename=config_filename,
        extrapolate_step=extrapolate_step,
        woa23_map_step=woa23_map_step,
    )

    jra55_map_step = component.get_or_create_shared_step(
        step_cls=Jra55MapStep,
        subdir=os.path.join(base_subdir, 'jra55_map'),
        config=config,
        config_filename=config_filename,
        stress_step=stress_step,
        cull_mesh_step=cull_mesh_step,
        mesh_name=mesh_name,
    )

    remap_jra55_step = component.get_or_create_shared_step(
        step_cls=RemapJra55Step,
        subdir=os.path.join(base_subdir, 'remap_jra55'),
        config=config,
        config_filename=config_filename,
        stress_step=stress_step,
        jra55_map_step=jra55_map_step,
        cull_mesh_step=cull_mesh_step,
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
        subdir=os.path.join(model_dir, 'initial_state'),
        config=model_config,
        config_filename=config_filename,
        pstar_init_step=pstar_init_step,
        cull_mesh_step=cull_mesh_step,
    )

    forcing_step = component.get_or_create_shared_step(
        step_cls=ForcingStep,
        subdir=os.path.join(model_dir, 'forcing'),
        config=model_config,
        config_filename=config_filename,
        remap_jra55_step=remap_jra55_step,
    )

    viz_step = component.get_or_create_shared_step(
        step_cls=VizInitStep,
        subdir=os.path.join(model_dir, 'viz'),
        config=model_config,
        config_filename=config_filename,
        init_step=init_step,
        cull_mesh_step=cull_mesh_step,
        remap_jra55_step=remap_jra55_step,
    )

    steps: dict[str, Step] = dict(cull_steps)
    steps.update(woa23_steps)
    steps.update(jra55_steps)
    steps[cull_topo_step.name] = cull_topo_step
    steps[woa23_map_step.name] = woa23_map_step
    steps[remap_step.name] = remap_step
    steps[jra55_map_step.name] = jra55_map_step
    steps[remap_jra55_step.name] = remap_jra55_step
    steps[pstar_init_step.name] = pstar_init_step
    steps[init_step.name] = init_step
    steps[forcing_step.name] = forcing_step
    if include_viz:
        steps[viz_step.name] = viz_step
    return steps, config


def init_subdir(mesh_name):
    """
    The work directory the init steps for a mesh live under.

    Parameters
    ----------
    mesh_name : str
        The name of the MPAS mesh.

    Returns
    -------
    str
        The subdirectory, relative to the component.
    """
    return f'spherical/realistic_global/{mesh_name}/init'


def _get_init_config(component, subdir, config_filename, mesh_name):
    """
    Get or create the shared per-mesh config for the realistic init steps.

    Per-mesh overrides from
    :py:mod:`polaris.tasks.ocean.realistic_global.mesh_configs` are added last
    so that they take precedence over the defaults in
    ``init.cfg``.

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        The ocean component.

    subdir : str
        The subdirectory path for this mesh's init steps.

    config_filename : str
        The config filename (symlinked in each step's work directory).

    mesh_name : str
        The name of the MPAS mesh, used to find per-mesh overrides.

    Returns
    -------
    polaris.config.PolarisConfigParser
    """
    filepath = os.path.join(component.name, subdir, config_filename)

    def create():
        config = PolarisConfigParser(filepath=filepath)
        # provides [mapping] map_tool, used by MappingFileStep
        config.add_from_package('polaris.remap', 'mapping.cfg')
        config.add_from_package(
            'polaris.tasks.ocean.realistic_global.init',
            config_filename,
        )
        add_realistic_global_mesh_config(config=config, mesh_name=mesh_name)
        return config

    return component.get_or_create_shared_config(
        filepath=filepath, create=create
    )
