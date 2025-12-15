from polaris import Component


class SeaIce(Component):
    def __init__(self):
        """
        Construct the collection of MPAS-Ocean test cases
        """
        super().__init__(name='seaice')


# create a single module-level instance available to other components
seaice = SeaIce()
