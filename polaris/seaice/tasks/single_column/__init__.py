from polaris import TestGroup
from polaris.seaice.tasks.single_column.exact_restart import ExactRestart
from polaris.seaice.tasks.single_column.standard_physics import StandardPhysics


class SingleColumn(TestGroup):
    """
    A test group for "single column" test cases
    """
    def __init__(self, component):
        """
        component : polaris.seaice
            the component that this test group belongs to
        """
        super().__init__(component=component, name='single_column')
        self.add_task(
            StandardPhysics(test_group=self))
        self.add_task(
            ExactRestart(test_group=self))
