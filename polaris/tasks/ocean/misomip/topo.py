from polaris.tasks.ocean.isomip_plus.topo import TopoMap


def get_smoothing_distance(resolution):
    """
    Get the distance over which MISOMIP smooths the geometry on the ocean:
    the width of one ocean cell.  Both the protocol's bed and MALI's geometry
    are smoothed over it, so that they are smoothed alike.

    Parameters
    ----------
    resolution : float
        The resolution of the ocean's mesh in km

    Returns
    -------
    expand_distance : float
        The distance in m by which each ocean cell is inflated
    """
    return 1e3 * resolution


class MisomipTopoMap(TopoMap):
    """
    A step for making the map of the protocol's bed to the ocean's mesh,
    whose ocean cells are inflated as those of the map of MALI's geometry
    are, so that the bed and the ice draft are smoothed alike

    Attributes
    ----------
    expand_distance : float
        The distance in m by which each ocean cell is inflated
    """

    def __init__(
        self,
        component,
        name,
        subdir,
        mesh_name,
        mesh_step,
        mesh_filename,
        expand_distance,
    ):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        name : str
            The name of the step

        subdir : str
            The subdirectory for the step

        mesh_name : str
            The name of the mesh

        mesh_step : polaris.Step
            The step that makes the ocean's culled mesh

        mesh_filename : str
            The name of the culled mesh in the mesh step's work directory

        expand_distance : float
            The distance in m by which each ocean cell is inflated, from
            :py:func:`get_smoothing_distance`
        """
        # the cells are inflated by a distance, not by the ISOMIP+ factor
        super().__init__(
            component=component,
            name=name,
            subdir=subdir,
            mesh_name=mesh_name,
            mesh_step=mesh_step,
            mesh_filename=mesh_filename,
            method='conserve',
            smooth=False,
        )
        self.expand_distance = expand_distance

    def runtime_setup(self):
        """
        Set how far the ocean cells are inflated, then the grids
        """
        self.remapper.expand_dist = self.expand_distance
        super().runtime_setup()
