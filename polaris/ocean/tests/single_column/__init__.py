from polaris import TestGroup
from polaris.ocean.tests.single_column.cvmix import CVMix


class SingleColumn(TestGroup):
    """
    A test group for single column test cases
    """
    def __init__(self, component):
        """
        component : polaris.ocean.Ocean
            the ocean component that this test group belongs to
        """
        super().__init__(component=component, name='single_column')

        self.add_test_case(CVMix(test_group=self, resolution=960.))
