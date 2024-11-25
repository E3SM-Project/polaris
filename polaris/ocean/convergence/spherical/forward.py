from polaris.ocean.convergence import get_resolution_for_task
from polaris.ocean.convergence.forward import ConvergenceForward


class SphericalConvergenceForward(ConvergenceForward):
    """
    A step for performing forward ocean component runs as part of a spherical
    convergence test

    Attributes
    ----------
    resolution : float
        The resolution of the (uniform) mesh in km

    package : Package
        The package name or module object that contains the YAML file

    yaml_filename : str
        A YAML file that is a Jinja2 template with model config options

    """

    def compute_cell_count(self):
        """
        Compute the approximate number of cells in the mesh, used to constrain
        resources

        Returns
        -------
        cell_count : int or None
            The approximate number of cells in the mesh
        """
        # use a heuristic based on QU30 (65275 cells) and QU240 (10383 cells)
        resolution = get_resolution_for_task(
            self.config, self.refinement_factor,
            refinement=self.refinement)
        cell_count = 6e8 / resolution**2
        return cell_count
