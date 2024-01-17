from polaris.mesh.planar import compute_planar_hex_nx_ny
from polaris.ocean.ice_shelf.ssh_forward import (
    SshForward as IceShelfSshForward,
)


class SshForward(IceShelfSshForward):
    """
    A step for performing forward ocean component runs as part of ssh
    adjustment.
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
        section = self.config['ice_shelf_2d']
        lx = section.getfloat('lx')
        ly = section.getfloat('ly')
        nx, ny = compute_planar_hex_nx_ny(lx, ly, self.resolution)
        cell_count = nx * ny
        return cell_count
