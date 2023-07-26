from polaris import TestGroup
from polaris.seaice.tests.single_column.exact_restart import ExactRestart
from polaris.seaice.tests.single_column.standard_physics import StandardPhysics


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
        self.add_test_case(
            StandardPhysics(test_group=self))
        self.add_test_case(
            ExactRestart(test_group=self))
