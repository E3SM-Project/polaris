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


class ThinFilmSshForward(SshForward):
    """
    A step for performing forward ocean component runs as part of ssh
    adjustment for ISOMIP+ tasks with a thin film under grounded ice, with
    the same wetting and drying options as their forward runs
    """

    def dynamic_model_config(self, at_setup):
        """
        Add the thin film's wetting and drying options after the other model
        config options

        Parameters
        ----------
        at_setup : bool
            Whether this method is being run during setup of the step, as
            opposed to at runtime
        """
        super().dynamic_model_config(at_setup)
        self.add_yaml_file(
            'polaris.tasks.ocean.isomip_plus', 'thin_film_wetting_drying.yaml'
        )
