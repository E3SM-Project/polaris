from typing import Dict

from polaris.tasks import TaskGroup, add_task_groups

# The task groups of the ocean component, in the order they are added.
# Nothing here is imported until a task group is added.
_OCEAN = 'polaris.tasks.ocean'
TASK_GROUPS: Dict[str, TaskGroup] = {
    # planar tasks
    'baroclinic_channel': TaskGroup(
        f'{_OCEAN}.baroclinic_channel', 'add_baroclinic_channel_tasks'
    ),
    'barotropic_channel': TaskGroup(
        f'{_OCEAN}.barotropic_channel', 'add_barotropic_channel_tasks'
    ),
    'barotropic_gyre': TaskGroup(
        f'{_OCEAN}.barotropic_gyre', 'add_barotropic_gyre_tasks'
    ),
    'horiz_press_grad': TaskGroup(
        f'{_OCEAN}.horiz_press_grad', 'add_horiz_press_grad_tasks'
    ),
    'ice_shelf_2d': TaskGroup(
        f'{_OCEAN}.ice_shelf_2d', 'add_ice_shelf_2d_tasks'
    ),
    'inertial_gravity_wave': TaskGroup(
        f'{_OCEAN}.inertial_gravity_wave', 'add_inertial_gravity_wave_tasks'
    ),
    'internal_wave': TaskGroup(
        f'{_OCEAN}.internal_wave', 'add_internal_wave_tasks'
    ),
    'isomip_plus/planar': TaskGroup(
        f'{_OCEAN}.isomip_plus',
        'add_isomip_plus_tasks',
        dict(mesh_type='planar'),
    ),
    'manufactured_solution': TaskGroup(
        f'{_OCEAN}.manufactured_solution', 'add_manufactured_solution_tasks'
    ),
    'overflow': TaskGroup(f'{_OCEAN}.overflow', 'add_overflow_tasks'),
    'merry_go_round': TaskGroup(
        f'{_OCEAN}.merry_go_round', 'add_merry_go_round_tasks'
    ),
    'mixed_layer_eddies': TaskGroup(
        f'{_OCEAN}.mixed_layer_eddies', 'add_mixed_layer_eddies_tasks'
    ),
    'seamount': TaskGroup(f'{_OCEAN}.seamount', 'add_seamount_tasks'),
    # single column tasks
    'single_column': TaskGroup(
        f'{_OCEAN}.single_column', 'add_single_column_tasks'
    ),
    # analysis of a completed simulation, which runs no model
    'analysis': TaskGroup(f'{_OCEAN}.analysis', 'add_analysis_tasks'),
    # spherical tasks
    'customizable_viz': TaskGroup(
        f'{_OCEAN}.customizable_viz', 'add_customizable_viz_tasks'
    ),
    'cosine_bell': TaskGroup(f'{_OCEAN}.cosine_bell', 'add_cosine_bell_tasks'),
    'external_gravity_wave': TaskGroup(
        f'{_OCEAN}.external_gravity_wave', 'add_external_gravity_wave_tasks'
    ),
    'feature_masks': TaskGroup(
        f'{_OCEAN}.feature_masks', 'add_feature_mask_tasks'
    ),
    'geostrophic': TaskGroup(f'{_OCEAN}.geostrophic', 'add_geostrophic_tasks'),
    'isomip_plus/spherical': TaskGroup(
        f'{_OCEAN}.isomip_plus',
        'add_isomip_plus_tasks',
        dict(mesh_type='spherical'),
    ),
    'realistic_global': TaskGroup(
        f'{_OCEAN}.realistic_global', 'add_realistic_global_tasks'
    ),
    'sphere_transport': TaskGroup(
        f'{_OCEAN}.sphere_transport', 'add_sphere_transport_tasks'
    ),
}


def add_ocean_tasks(component, task_groups=None):
    """
    Add tasks to the ocean component

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        The ocean component to which tasks will be added.

    task_groups : list of str, optional
        The task groups to add, by default all of them
    """
    add_task_groups(component, task_groups)
