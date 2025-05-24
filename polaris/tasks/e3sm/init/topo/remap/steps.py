import os

from polaris.config import PolarisConfigParser
from polaris.step import Step
from polaris.tasks.e3sm.init.topo.remap.mask import MaskTopoStep
from polaris.tasks.e3sm.init.topo.remap.remap import RemapTopoStep
from polaris.tasks.e3sm.init.topo.remap.viz import VizRemappedTopoStep


def get_default_remap_topo_steps(
    component,
    base_mesh_step,
    combine_topo_step,
    low_res,
    smoothing=False,
    include_viz=False,
):
    """
    Add a steps for compting a mapping file and then remapping bathymetry and
    ice-shelf topography from a cubed-sphere grid to a global MPAS base mesh.
    The unsmoothed topography will typically be used to determine coastlines
    for mesh culling and related masks so that they are independent of
    smoothing choices (e.g. so mapping files can be reused with different
    smoothing choices).  The smoothed topography will be used for the actual
    bathymetry, land surface elevation, land-ice pressure, etc.

    Parameters
    ----------
    component : polaris.Component
        The component the steps belong to

    base_mesh_step : polaris.mesh.spherical.SphericalBaseStep
        The base mesh step containing input files to this step

    combine_topo_step : polaris.tasks.e3sm.init.topo.CombineStep
        The step for combining global and Antarctic topography on a cubed
        sphere grid

    low_res : bool
        Whether the base mesh is low resolution (120km or coarser), so that
        a set of config options for low resolution and a lower resolution
        source topography should be used

    smoothing : bool, optional
        Whether to create a step with smoothing in addition to the step without
        smoothing

    include_viz : bool, optional
        Whether to include visualization steps

    Returns
    -------
    steps : list of polaris.Step
        Steps for remapping topography (without smoothing and optionally with
        smoothing) as well as, if requested, for visualizing the results.
    """

    mesh_name = base_mesh_step.mesh_name

    # add default config options for remapping topo -- since these are
    # shared step, the config options need to be defined separately from any
    # task this may be added to
    config_filename = 'remap_topo.cfg'
    filepath = os.path.join(
        component.name, mesh_name, 'topo', 'remap', config_filename
    )
    config = PolarisConfigParser(filepath=filepath)
    config.add_from_package('polaris.tasks.e3sm.init.topo.remap', 'remap.cfg')
    if low_res:
        config.add_from_package(
            'polaris.tasks.e3sm.init.topo.remap', 'remap_low_res.cfg'
        )
    steps: list[Step] = []

    step_name = 'mask_topo'
    subdir = os.path.join(mesh_name, 'topo', 'remap', 'mask')
    mask_step = MaskTopoStep(
        component=component,
        config=config,
        combine_topo_step=combine_topo_step,
        name=step_name,
        subdir=subdir,
    )
    steps.append(mask_step)

    if smoothing:
        suffixes = ['unsmoothed', 'smoothed']
    else:
        suffixes = ['unsmoothed']

    unsmoothed_topo = None
    for suffix in suffixes:
        step_name = f'remap_{suffix}'
        subdir = os.path.join(mesh_name, 'topo', 'remap', suffix)
        remap_step = RemapTopoStep(
            component=component,
            config=config,
            base_mesh_step=base_mesh_step,
            mask_topo_step=mask_step,
            combine_topo_step=combine_topo_step,
            name=step_name,
            subdir=subdir,
            smoothing=(suffix == 'smoothed'),
            unsmoothed_topo=unsmoothed_topo,
        )
        if suffix == 'unsmoothed':
            unsmoothed_topo = remap_step
        component.add_step(remap_step)
        steps.append(remap_step)

        if include_viz:
            step_name = f'viz_remapped_{suffix}'
            subdir = os.path.join(str(subdir), 'viz')
            viz_step = VizRemappedTopoStep(
                component=component,
                name=step_name,
                subdir=subdir,
                remap_step=remap_step,
            )
            component.add_step(viz_step)
            steps.append(viz_step)

    return steps, config
