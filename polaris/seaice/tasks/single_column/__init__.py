from polaris.seaice.tasks.single_column.exact_restart import (
    ExactRestart as ExactRestart,
)
from polaris.seaice.tasks.single_column.standard_physics import (
    StandardPhysics as StandardPhysics,
)


def add_single_column_tasks(component):
    """
    Add various tasks that define single-column tests

    Parameters
    ----------
    component : polaris.seaice.Seaice
        the component that that the tasks will be added to
    """
    component.add_task(StandardPhysics(component=component))
    component.add_task(ExactRestart(component=component))
