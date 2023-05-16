from polaris import TestCase


class TestBalance(TestCase):
    """
    The default test case for the "galewsky jet" test group simply creates
    the mesh and initial condition, then performs a short forward run on 4
    cores.
    """

    def __init__(self, test_group):
        """
        Create the test case

        Parameters
        ----------
        test_group : polaris.ocean.tests.galewsky_jet.GalewskyJet
            The test group that this test case belongs to
        """
        name = 'test_balance'
        super().__init__(test_group=test_group, name=name)
