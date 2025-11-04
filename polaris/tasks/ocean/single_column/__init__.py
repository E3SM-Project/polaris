from polaris.tasks.ocean.single_column.cvmix import CVMix as CVMix
from polaris.tasks.ocean.single_column.ekman import Ekman as Ekman
from polaris.tasks.ocean.single_column.ideal_age import IdealAge as IdealAge
from polaris.tasks.ocean.single_column.inertial import Inertial as Inertial


def add_single_column_tasks(component):
    """
    Add tasks for various single-column tests

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        the ocean component that the tasks will be added to
    """
    component.add_task(Ekman(component=component))
    component.add_task(CVMix(component=component))
    component.add_task(IdealAge(component=component))
    component.add_task(Inertial(component=component))
