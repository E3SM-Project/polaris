from polaris import Component as Component
from polaris.tasks.seaice.single_column import (
    add_single_column_tasks as add_single_column_tasks,
)


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
