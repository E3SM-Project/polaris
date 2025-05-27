import os

from polaris.config import PolarisConfigParser
from polaris.step import Step
from polaris.tasks.e3sm.init.topo.cull.mask import CullMaskStep


def get_default_cull_topo_steps(
    component,
    base_mesh_step,
    unsmoothed_topo_step,
    include_viz=False,
):
    """
    Add a steps for creating a mask for the ocean (with and without ice-shelf
    cavities) and the land, and then for culling the base mesh to each of these
    regions.

    Parameters
    ----------
    component : polaris.Component
        The component the steps belong to

    base_mesh_step : polaris.mesh.spherical.SphericalBaseStep
        The base mesh step containing input files to this step

    unsmoothed_topo_step : polaris.tasks.e3sm.init.topo.remap.RemapTopoStep
        The step for remapping the unsmoothed topography

    include_viz : bool, optional
        Whether to include a visualization step

    Returns
    -------
    steps : list of polaris.Step
        Steps for masking and then culling topography
    """

    mesh_name = base_mesh_step.mesh_name

    # add default config options for culling topo -- since these are
    # shared step, the config options need to be defined separately from any
    # task this may be added to
    config_filename = 'cull_topo.cfg'
    filepath = os.path.join(
        component.name, mesh_name, 'topo', 'cull', config_filename
    )
    config = PolarisConfigParser(filepath=filepath)
    config.add_from_package('polaris.tasks.e3sm.init.topo.cull', 'cull.cfg')
    steps: list[Step] = []

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
    steps.append(cull_mask_step)

    return steps, config
