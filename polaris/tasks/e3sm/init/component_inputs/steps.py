import os

from polaris.config import PolarisConfigParser
from polaris.mesh.spherical.unified import UNIFIED_MESH_NAMES
from polaris.step import Step
from polaris.tasks.e3sm.init import e3sm_init
from polaris.tasks.e3sm.init.component_inputs.base_mesh import BaseMeshStep
from polaris.tasks.e3sm.init.component_inputs.ocean_graph_partition import (
    OceanGraphPartitionStep,
)
from polaris.tasks.e3sm.init.component_inputs.ocean_initial_condition import (
    OceanInitialConditionStep,
)
from polaris.tasks.e3sm.init.component_inputs.ocean_mesh import OceanMeshStep
from polaris.tasks.e3sm.init.component_inputs.scrip import ScripStep
from polaris.tasks.e3sm.init.topo.cull.steps import get_cull_topo_steps
from polaris.tasks.ocean import ocean
from polaris.tasks.ocean.realistic_global.dynamic_adjustment.steps import (
    get_realistic_dynamic_adjustment_steps,
)

CONFIG_FILENAME = 'component_inputs.cfg'
CONFIG_PACKAGE = 'polaris.tasks.e3sm.init.component_inputs'


def get_component_inputs_steps(mesh_name):
    """
    Get shared steps for staging E3SM component input files for one mesh.

    Composes the full dependency chain: the upstream cull-topography steps
    from ``e3sm/init`` (via
    :py:func:`~polaris.tasks.e3sm.init.topo.cull.steps.get_cull_topo_steps`),
    then the steps that stage products from them.

    All steps are created via
    :py:meth:`polaris.Component.get_or_create_shared_step`, so the three tasks
    that share most of these steps get the same instances rather than three
    copies of the work.

    Parameters
    ----------
    mesh_name : str
        The name of the base mesh to stage component inputs for.

    Returns
    -------
    steps : dict of {str: polaris.Step}
        All upstream shared steps plus the component-input steps, keyed by
        their suggested symlink names.

    config : polaris.config.PolarisConfigParser
        The shared config options for the component-input steps.
    """
    component = e3sm_init
    cull_steps, _ = get_cull_topo_steps(mesh_name=mesh_name, include_viz=False)
    base_mesh_step = cull_steps['base_mesh']
    cull_mesh_step = cull_steps['cull_mesh']

    base_subdir = component_inputs_subdir(mesh_name)
    config = _get_component_inputs_config(base_subdir, mesh_name)

    steps: dict[str, Step] = dict(cull_steps)

    # only a mesh that was actually culled has culled meshes to map to
    with_maps = mesh_name in UNIFIED_MESH_NAMES

    base_mesh = component.get_or_create_shared_step(
        step_cls=BaseMeshStep,
        subdir=os.path.join(base_subdir, 'base_mesh'),
        config=config,
        config_filename=CONFIG_FILENAME,
        base_mesh_step=base_mesh_step,
        cull_mesh_step=cull_mesh_step,
        with_maps=with_maps,
    )
    steps['staged_base_mesh'] = base_mesh

    scrip = component.get_or_create_shared_step(
        step_cls=ScripStep,
        subdir=os.path.join(base_subdir, 'scrip'),
        config=config,
        config_filename=CONFIG_FILENAME,
        cull_mesh_step=cull_mesh_step,
    )
    steps['scrip'] = scrip

    _add_ocean_steps(
        steps=steps,
        config=config,
        base_subdir=base_subdir,
        mesh_name=mesh_name,
        cull_mesh_step=cull_mesh_step,
    )

    return steps, config


def _add_ocean_steps(steps, config, base_subdir, mesh_name, cull_mesh_step):
    """
    Add the MPAS-Ocean products, and the upstream ocean steps they need.

    The initial condition comes from the last dynamic-adjustment stage rather
    than from the initial state, so this pulls in the whole adjustment chain
    as shared steps.  Those live in the ocean component; only the steps that
    stage files belong to ``e3sm/init``.
    """
    adjustment_steps, _, stages = get_realistic_dynamic_adjustment_steps(
        component=ocean, mesh_name=mesh_name, include_viz=False
    )
    steps.update(adjustment_steps)

    ocean_mesh = e3sm_init.get_or_create_shared_step(
        step_cls=OceanMeshStep,
        subdir=os.path.join(base_subdir, 'ocean_mesh'),
        config=config,
        config_filename=CONFIG_FILENAME,
        init_step=adjustment_steps['initial_state'],
    )
    steps['ocean_mesh'] = ocean_mesh

    final_stage = stages[-1]
    ocean_initial_condition = e3sm_init.get_or_create_shared_step(
        step_cls=OceanInitialConditionStep,
        subdir=os.path.join(base_subdir, 'ocean_initial_condition'),
        config=config,
        config_filename=CONFIG_FILENAME,
        forward_step=adjustment_steps[final_stage.name],
        restart_filename=final_stage.restart_out,
    )
    steps['ocean_initial_condition'] = ocean_initial_condition

    ocean_graph_partition = e3sm_init.get_or_create_shared_step(
        step_cls=OceanGraphPartitionStep,
        subdir=os.path.join(base_subdir, 'ocean_graph_partition'),
        config=config,
        config_filename=CONFIG_FILENAME,
        cull_mesh_step=cull_mesh_step,
    )
    steps['ocean_graph_partition'] = ocean_graph_partition


def component_inputs_subdir(mesh_name):
    """
    The work directory the component-input steps for a mesh live under.

    Parameters
    ----------
    mesh_name : str
        The name of the base mesh.

    Returns
    -------
    str
        The subdirectory, relative to the component.
    """
    return os.path.join(mesh_name, 'component_inputs')


def _get_component_inputs_config(base_subdir, mesh_name):
    """
    Get or create the shared per-mesh config for the component-input steps.

    The unified-mesh config comes along because that is where a mesh's E3SM
    short name is registered.
    """
    filepath = os.path.join(e3sm_init.name, base_subdir, CONFIG_FILENAME)

    def create():
        config = PolarisConfigParser(filepath=filepath)
        config.add_from_package(CONFIG_PACKAGE, CONFIG_FILENAME)
        if mesh_name in UNIFIED_MESH_NAMES:
            config.add_from_package(
                'polaris.mesh.spherical.unified', 'unified_mesh.cfg'
            )
            config.add_from_package(
                'polaris.mesh.spherical.unified', f'{mesh_name}.cfg'
            )
        return config

    return e3sm_init.get_or_create_shared_config(
        filepath=filepath, create=create
    )
