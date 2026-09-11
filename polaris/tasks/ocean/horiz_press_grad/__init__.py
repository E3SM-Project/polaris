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
    # model's HPGA is the error and no reference solution is needed.  The two
    # _linear variants are additionally inside the finite-volume scheme's exact
    # set, so their residual is the scheme's own rather than the profile's;
    # bathymetry_step_linear is the only one that is both exact and in the
    # geometry that matters globally.
    for name in [
        'bathymetry_step',
        'bathymetry_step_linear',
        'hydrostatic_consistency',
        'hydrostatic_consistency_linear',
    ]:
        component.add_task(
            HorizPressGradRestingStateTask(component=component, name=name)
        )
