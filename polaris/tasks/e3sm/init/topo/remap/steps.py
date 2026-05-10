import os

from polaris.config import PolarisConfigParser
from polaris.e3sm.init.topo import (
    get_cubed_sphere_resolution,
    uses_low_res_cubed_sphere,
)
from polaris.step import Step
from polaris.tasks.e3sm.init import e3sm_init
from polaris.tasks.e3sm.init.topo.combine import get_cubed_sphere_topo_steps
from polaris.tasks.e3sm.init.topo.combine.step import CombineStep
from polaris.tasks.e3sm.init.topo.remap.mask import MaskTopoStep
from polaris.tasks.e3sm.init.topo.remap.remap import RemapTopoStep
from polaris.tasks.e3sm.init.topo.remap.viz import VizRemappedTopoStep
from polaris.tasks.mesh.base.steps import get_base_mesh_steps


def get_remap_topo_steps(mesh_name, smoothing=False, include_viz=False):
    """
    Get shared steps for computing a mapping file and then remapping
    bathymetry and ice-shelf topography from a cubed-sphere grid to a global
    MPAS base mesh.
    The unsmoothed topography will typically be used to determine coastlines
    for mesh culling and related masks so that they are independent of
    smoothing choices (e.g. so mapping files can be reused with different
    smoothing choices).  The smoothed topography will be used for the actual
    bathymetry, land surface elevation, land-ice pressure, etc.

    Parameters
    ----------
    mesh_name : str
        The name of the base mesh to remap topography onto

    smoothing : bool, optional
        Whether to create a step with smoothing in addition to the step without
        smoothing

    include_viz : bool, optional
        Whether to include visualization steps

    Returns
    -------
    steps : dict of str to polaris.Step
        All upstream shared steps plus the steps for remapping topography
        (without smoothing and optionally with smoothing) as well as, if
        requested, for visualizing the results, keyed by suggested symlink
        in tasks.

    config : polaris.config.PolarisConfigParser
        The shared config options for remapping topography.
    """
    component = e3sm_init
    base_mesh_steps, base_mesh_config = get_base_mesh_steps(
        mesh_name=mesh_name, include_viz=False
    )
    base_mesh_step = base_mesh_steps['base_mesh']

    max_cell_width = base_mesh_config.getfloat(
        'spherical_mesh', 'max_cell_width'
    )
    low_res = uses_low_res_cubed_sphere(max_cell_width)
    resolution = get_cubed_sphere_resolution(low_res)
    combine_topo_steps, _ = get_cubed_sphere_topo_steps(
        component=component,
        resolution=resolution,
        include_viz=False,
    )

    resolution_name = f'ne{resolution}'
    combine_step_name = CombineStep.get_name(
        target_grid='cubed_sphere', resolution_name=resolution_name
    )
    combine_topo_step = combine_topo_steps[combine_step_name]
    # the combined topography is expensive to create, so cache it for reuse
    combine_topo_step.cached = True
    combine_topo_key = f'combine_topo_cubed_sphere_{resolution_name}'

    config_filename = 'remap_topo.cfg'
    filepath = os.path.join(
        component.name, mesh_name, 'topo', 'remap', config_filename
    )
    config = _get_remap_topo_config(
        filepath=filepath,
        base_mesh_step=base_mesh_step,
        low_res=low_res,
    )

    steps: dict[str, Step] = dict(base_mesh_steps)
    steps[combine_topo_key] = combine_topo_step

    step_name = 'mask_topo'
    subdir = os.path.join(mesh_name, 'topo', 'remap', 'mask')
    mask_step = component.get_or_create_shared_step(
        step_cls=MaskTopoStep,
        subdir=subdir,
        config=config,
        config_filename=config_filename,
        combine_topo_step=combine_topo_step,
        name=step_name,
    )
    steps['mask_topo'] = mask_step

    if smoothing:
        suffixes = ['unsmoothed', 'smoothed']
    else:
        suffixes = ['unsmoothed']

    unsmoothed_topo = None
    for suffix in suffixes:
        step_name = f'remap_{suffix}'
        subdir = os.path.join(mesh_name, 'topo', 'remap', suffix)
        remap_step = component.get_or_create_shared_step(
            step_cls=RemapTopoStep,
            subdir=subdir,
            config=config,
            config_filename=config_filename,
            base_mesh_step=base_mesh_step,
            mask_topo_step=mask_step,
            combine_topo_step=combine_topo_step,
            name=step_name,
            smoothing=(suffix == 'smoothed'),
            unsmoothed_topo=unsmoothed_topo,
        )

        if suffix == 'unsmoothed':
            unsmoothed_topo = remap_step
            steps['remap_unsmoothed_topo'] = remap_step
        else:
            steps['remap_smoothed_topo'] = remap_step

        if include_viz:
            step_name = f'viz_remapped_{suffix}'
            subdir = os.path.join(str(subdir), 'viz')
            viz_step = component.get_or_create_shared_step(
                step_cls=VizRemappedTopoStep,
                subdir=subdir,
                config=config,
                config_filename=config_filename,
                remap_step=remap_step,
                name=step_name,
            )
            steps[f'viz_remapped_{suffix}_topo'] = viz_step

    return steps, config


def _get_remap_topo_config(filepath, base_mesh_step, low_res):
    component = e3sm_init
    if filepath in component.configs:
        return component.configs[filepath]

    config = PolarisConfigParser(filepath=filepath)
    config.add_from_package('polaris.tasks.e3sm.init.topo.remap', 'remap.cfg')
    if low_res:
        config.add_from_package(
            'polaris.tasks.e3sm.init.topo.remap', 'remap_low_res.cfg'
        )
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
