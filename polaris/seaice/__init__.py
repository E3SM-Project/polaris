from polaris import Component
from polaris.seaice.tests.single_column import SingleColumn


class SeaIce(Component):
    """
    The collection of all test case for the MPAS-Seaice component
    """

    def __init__(self):
        """
        Construct the collection of MPAS-Seaice test cases
        """
        super().__init__(name='seaice')

        # please keep these in alphabetical order
        self.add_test_group(SingleColumn(component=self))
