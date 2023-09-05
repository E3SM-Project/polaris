from polaris import TestGroup
from polaris.ocean.tasks.single_column.cvmix import CVMix
from polaris.ocean.tasks.single_column.ideal_age import IdealAge


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

        self.add_task(CVMix(test_group=self, resolution=960.))
        self.add_task(IdealAge(test_group=self, resolution=960.))
