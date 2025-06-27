from polaris.tasks.ocean.baroclinic_channel import add_baroclinic_channel_tasks
from polaris.tasks.ocean.barotropic_channel import add_barotropic_channel_tasks
from polaris.tasks.ocean.barotropic_gyre import add_barotropic_gyre_tasks
from polaris.tasks.ocean.cosine_bell import add_cosine_bell_tasks
from polaris.tasks.ocean.customizable_viz import add_customizable_viz_tasks
from polaris.tasks.ocean.external_gravity_wave import (
    add_external_gravity_wave_tasks as add_external_gravity_wave_tasks,
)
from polaris.tasks.ocean.geostrophic import add_geostrophic_tasks
from polaris.tasks.ocean.ice_shelf_2d import add_ice_shelf_2d_tasks
from polaris.tasks.ocean.inertial_gravity_wave import (
    add_inertial_gravity_wave_tasks as add_inertial_gravity_wave_tasks,
)
from polaris.tasks.ocean.internal_wave import add_internal_wave_tasks
from polaris.tasks.ocean.isomip_plus import add_isomip_plus_tasks
from polaris.tasks.ocean.manufactured_solution import (
    add_manufactured_solution_tasks as add_manufactured_solution_tasks,
)
from polaris.tasks.ocean.merry_go_round import add_merry_go_round_tasks
from polaris.tasks.ocean.overflow import add_overflow_tasks
from polaris.tasks.ocean.single_column import add_single_column_tasks
from polaris.tasks.ocean.sphere_transport import add_sphere_transport_tasks


def add_ocean_tasks(component):
    """
    Add all ocean-related tasks to the ocean component.

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        The ocean component to which tasks will be added.
    """
    # planar tasks
    add_baroclinic_channel_tasks(component=component)
    add_barotropic_channel_tasks(component=component)
    add_barotropic_gyre_tasks(component=component)
    add_ice_shelf_2d_tasks(component=component)
    add_inertial_gravity_wave_tasks(component=component)
    add_internal_wave_tasks(component=component)
    add_isomip_plus_tasks(component=component, mesh_type='planar')
    add_manufactured_solution_tasks(component=component)
    add_overflow_tasks(component=component)
    add_merry_go_round_tasks(component=component)

    # single column tasks
    add_single_column_tasks(component=component)

    # spherical tasks
    add_customizable_viz_tasks(component=component)
    add_cosine_bell_tasks(component=component)
    add_external_gravity_wave_tasks(component=component)
    add_geostrophic_tasks(component=component)
    add_isomip_plus_tasks(component=component, mesh_type='spherical')
    add_sphere_transport_tasks(component=component)
