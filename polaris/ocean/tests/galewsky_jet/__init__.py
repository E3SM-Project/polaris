from polaris import TestGroup
from polaris.ocean.tests.galewsky_jet.test_balance import TestBalance
from polaris.ocean.tests.galewsky_jet.short_adjustment import ShortAdjustment
from polaris.ocean.tests.galewsky_jet.barotropic_instability import BarotropicInstability


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

        for resolution in [120.]:
            self.add_test_case(
                TestBalance(test_group=self, resolution=resolution))
            self.add_test_case(
                ShortAdjustment(test_group=self, resolution=resolution))
            self.add_test_case(
                BarotropicInstability(test_group=self, resolution=resolution))
