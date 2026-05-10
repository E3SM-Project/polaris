import os

from polaris.config import PolarisConfigParser
from polaris.step import Step
from polaris.tasks.e3sm.init import e3sm_init
from polaris.tasks.e3sm.init.topo.cull.cull import CullMeshStep
from polaris.tasks.e3sm.init.topo.cull.mask import CullMaskStep
from polaris.tasks.e3sm.init.topo.remap.steps import get_remap_topo_steps


def get_cull_topo_steps(mesh_name, include_viz=False):
    """
    Get shared steps for masking and culling topography for one base mesh.

    Includes all upstream remap-topography steps and then adds the steps for
    creating cull masks for the ocean (with and without ice-shelf cavities)
    and the land, followed by culling the base mesh to each of these regions.

    Parameters
    ----------
    mesh_name : str
        The name of the base mesh to cull

    include_viz : bool, optional
        Whether to include upstream remap visualization steps

    Returns
    -------
    steps : dict of str to polaris.Step
        All upstream shared steps plus the cull-mask and cull-mesh steps,
        keyed by suggested symlink in tasks.

    config : polaris.config.PolarisConfigParser
        The shared config options for culling topography.
    """
    component = e3sm_init
    remap_steps, _ = get_remap_topo_steps(
        mesh_name=mesh_name,
        smoothing=True,
        include_viz=False,
    )
    base_mesh_step = remap_steps['base_mesh']
    unsmoothed_topo_step = remap_steps['remap_unsmoothed_topo']

    config_filename = 'cull_topo.cfg'
    filepath = os.path.join(
        component.name, mesh_name, 'topo', 'cull', config_filename
    )
    config = _get_cull_topo_config(
        filepath=filepath,
        base_mesh_step=base_mesh_step,
    )

    steps: dict[str, Step] = dict(remap_steps)

    step_name = 'cull_mask'
    subdir = os.path.join(mesh_name, 'topo', 'cull', 'mask')
    cull_mask_step = component.get_or_create_shared_step(
        step_cls=CullMaskStep,
        subdir=subdir,
        config=config,
        config_filename=config_filename,
        base_mesh_step=base_mesh_step,
        unsmoothed_topo_step=unsmoothed_topo_step,
        name=step_name,
    )
    steps['cull_mask'] = cull_mask_step

    step_name = 'cull_mesh'
    subdir = os.path.join(mesh_name, 'topo', 'cull', 'mesh')
    cull_mesh_step = component.get_or_create_shared_step(
        step_cls=CullMeshStep,
        subdir=subdir,
        config=config,
        config_filename=config_filename,
        base_mesh_step=base_mesh_step,
        cull_mask_step=cull_mask_step,
        name=step_name,
    )
    steps['cull_mesh'] = cull_mesh_step

    return steps, config


def _get_cull_topo_config(filepath, base_mesh_step):
    component = e3sm_init
    if filepath in component.configs:
        return component.configs[filepath]

    config = PolarisConfigParser(filepath=filepath)
    config.add_from_package('polaris.tasks.e3sm.init.topo.cull', 'cull.cfg')
    config.add_from_package('polaris.mesh.spherical', 'spherical.cfg')

    convention = base_mesh_step.config.get(
        'spherical_mesh', 'antarctic_boundary_convention'
    )
    config.set(
        'spherical_mesh',
        'antarctic_boundary_convention',
        convention,
    )
    return config
