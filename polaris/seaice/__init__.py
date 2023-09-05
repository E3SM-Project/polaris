from polaris import Component
from polaris.seaice.tasks.single_column import add_single_column_tasks


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
        add_single_column_tasks(component=self)
