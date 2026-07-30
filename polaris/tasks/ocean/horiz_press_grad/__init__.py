from polaris.tasks.ocean.horiz_press_grad.resting_state_task import (
    HorizPressGradRestingStateTask,
)
from polaris.tasks.ocean.horiz_press_grad.task import HorizPressGradTask


def add_horiz_press_grad_tasks(component):
    """
    Add tasks for various tests involving the horizonal pressure-gradient
    acceleration between two adjacent ocean columns

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        the ocean component that the tasks will be added to
    """
    # variants with a horizontal gradient in a prescribed field, compared
    # against the quasi-analytic reference solution
    for name in [
        'salinity_gradient',
        'surface_pressure_gradient',
        'temperature_gradient',
        'ztilde_gradient',
    ]:
        component.add_task(HorizPressGradTask(component=component, name=name))

    # exact resting states, in which the true HPGA is identically zero, so the
    # model's HPGA is the error and no reference solution is needed.
    # hydrostatic_consistency_linear is additionally in the finite-volume
    # scheme's exact set, so it is the only one of these where machine
    # precision is the correct expectation.
    for name in [
        'bathymetry_step',
        'hydrostatic_consistency',
        'hydrostatic_consistency_linear',
    ]:
        component.add_task(
            HorizPressGradRestingStateTask(component=component, name=name)
        )
