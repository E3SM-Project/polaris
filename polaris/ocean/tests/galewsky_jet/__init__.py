from polaris import TestGroup
from polaris.ocean.tests.galewsky_jet.test_balance import TestBalance


class GalewskyJet(TestGroup):
    """
    A test group for "galewsky jet" test cases
    """
    def __init__(self, component):
        """
        component : polaris.ocean.Ocean
            the ocean component that this test group belongs to
        """
        super().__init__(component=component, name='galewsky_jet')

        self.add_test_case(
            TestBalance(test_group=self))
