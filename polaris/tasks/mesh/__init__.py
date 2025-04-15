from polaris import Component as Component


class Mesh(Component):
    """
    The collection of tasks and steps for making spherical (global) MPAS meshes
    """

    def __init__(self):
        """
        Construct the collection of MPAS-Mesh test cases
        """
        super().__init__(name='mesh')

        # please keep these in alphabetical order
