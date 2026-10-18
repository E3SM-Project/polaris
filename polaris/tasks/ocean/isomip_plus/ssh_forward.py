from polaris.ocean.ice_shelf.ssh_forward import (
    SshForward as IceShelfSshForward,
)
from polaris.tasks.ocean.isomip_plus.cell_count import estimate_cell_count
from polaris.tasks.ocean.isomip_plus.physics import (
    add_com_physics_yaml,
    get_physics_replacements,
)


class SshForward(IceShelfSshForward):
    """
    A step for performing forward ocean component runs as part of ssh
    adjustment for ISOMIP+ tasks, with the physics of the forward run
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

    def dynamic_model_config(self, at_setup):
        """
        Add model config options, namelist, streams and yaml files using config
        options or template replacements that need to be set both during step
        setup and at runtime

        Parameters
        ----------
        at_setup : bool
            Whether this method is being run during setup of the step, as
            opposed to at runtime
        """
        # the framework adds physics.yaml with these replacements
        self.yaml_replacements = get_physics_replacements(
            self.config, self.min_resolution
        )
        super().dynamic_model_config(at_setup)
        add_com_physics_yaml(self)
