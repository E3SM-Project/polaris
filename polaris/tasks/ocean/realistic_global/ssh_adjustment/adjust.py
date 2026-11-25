from polaris.ocean.ice_shelf import SshAdjustment
from polaris.ocean.init_state import apply_min_max_layer_thickness


class RealisticSshAdjustment(SshAdjustment):
    """
    A step that adjusts the sea-surface height under land ice so that it
    cancels the depth-mean acceleration of a single step from rest, leaving
    the land-ice pressure unchanged, for a realistic global ocean with
    ice-shelf cavities.

    The layer thicknesses follow the adjusted sea-surface height as
    MPAS-Ocean's z-star coordinate places them, with its minimum layer
    thickness, since the p-star coordinate of the initial condition has no
    counterpart in MPAS-Ocean.
    """

    def update_layer_thickness(self, ds):
        """
        Update the layer thicknesses in ``ds`` to match its adjusted SSH.

        Parameters
        ----------
        ds : xarray.Dataset
            The adjusted initial state, with the new ``ssh``, modified in
            place
        """
        section = self.config['realistic_global_cavities']
        apply_min_max_layer_thickness(
            ds,
            min_thickness=section.getfloat('thin_film_layer_thickness'),
            max_thickness_factor=section.getfloat(
                'max_layer_thickness_factor'
            ),
        )
