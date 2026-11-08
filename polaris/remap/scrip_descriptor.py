import os
import shutil

from pyremap.descriptor.mesh_descriptor import MeshDescriptor


class ScripFileDescriptor(MeshDescriptor):
    """
    A mesh described by an existing SCRIP file

    Attributes
    ----------
    filename : str
        The path of the SCRIP file
    """

    def __init__(self, filename, mesh_name, regional):
        """
        Create the descriptor

        Parameters
        ----------
        filename : str
            The path of the SCRIP file

        mesh_name : str
            The name of the mesh, used to give mapping files unique names

        regional : bool
            Whether the mesh is regional rather than global
        """
        super().__init__(mesh_name=mesh_name, regional=regional)
        self.filename = filename

    def to_scrip(self, scrip_filename, expand_dist=None, expand_factor=None):
        """
        Copy the SCRIP file to where the mapping tool reads it

        Parameters
        ----------
        scrip_filename : str
            The path to which the SCRIP file should be copied

        expand_dist : None
            Must be ``None``, since the cells of a SCRIP file can't be
            expanded

        expand_factor : None
            Must be ``None``, since the cells of a SCRIP file can't be
            expanded
        """
        if expand_dist is not None or expand_factor is not None:
            raise ValueError('The cells of a SCRIP file cannot be expanded.')
        if os.path.abspath(scrip_filename) != os.path.abspath(self.filename):
            shutil.copyfile(self.filename, scrip_filename)
