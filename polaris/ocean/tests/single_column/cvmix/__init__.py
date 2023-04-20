from polaris import TestCase


class CVMix(TestCase):
    """
    The default test case for the single column test group simply creates
    the mesh and initial condition, then performs a short forward run on 4
    cores.
    """
    def __init__(self, test_group):
        """
        Create the test case
        Parameters
        ----------
        test_group : polaris.ocean.tests.single_column.SingleColumn
            The test group that this test case belongs to
        """
        name = 'cvmix'
        super().__init__(test_group=test_group, name=name)
