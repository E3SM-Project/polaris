from polaris.ocean.ice_shelf.ssh_forward import (
    SshForward as IceShelfSshForward,
)
from polaris.tasks.ocean.isomip_plus.cell_count import estimate_cell_count


class SshForward(IceShelfSshForward):
    """
    A step for performing forward ocean component runs as part of ssh
    adjustment for ISOMIP+ tasks, with the ISOMIP+ equation of state
    """

    def __init__(self, **kwargs):
        """
        Create the step

        Parameters
        ----------
        kwargs : dict
            Arguments passed on to
            :py:class:`polaris.ocean.ice_shelf.ssh_forward.SshForward`
        """
        super().__init__(**kwargs)
        self.update_eos = True

    def compute_cell_count(self):
        """
        Compute the approximate number of cells in the mesh, used to constrain
        resources

        Returns
        -------
        cell_count : int or None
            The approximate number of cells in the mesh
        """
        return estimate_cell_count(self.config, self.min_resolution)
