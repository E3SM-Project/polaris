import mpas_tools.mesh.creation.mesh_definition_tools as mdt
import numpy as np


class DefaultUnifiedMeshFamily:
    """
    The default unified-mesh family for built-in ocean backgrounds.
    """

    name = 'default'

    def setup_sizing_field_step(self, step):
        """
        Add any family-specific sizing-field inputs.
        """

    def build_ocean_background(self, ds_coastline, section):
        """
        Build the family ocean background on the shared target grid.
        """
        return build_ocean_background_from_mode(
            lat=ds_coastline.lat.values,
            lon=ds_coastline.lon.values,
            mode=section.get('ocean_background_mode'),
            min_km=section.getfloat('ocean_background_min_km'),
            max_km=section.getfloat('ocean_background_max_km'),
        )


def build_ocean_background_from_mode(lat, lon, mode, min_km, max_km):
    """
    Build a 2D ocean-background field in km from the default family modes.
    """
    if mode == 'constant':
        if not np.isclose(min_km, max_km):
            raise ValueError(
                'Constant ocean backgrounds require '
                'ocean_background_min_km and '
                'ocean_background_max_km to be equal.'
            )
        values = np.full((lat.size, lon.size), max_km, dtype=float)
    elif mode == 'rrs_latitude':
        cell_width_vs_lat = mdt.RRS_CellWidthVsLat(
            lat, cellWidthEq=max_km, cellWidthPole=min_km
        )
        values = np.outer(cell_width_vs_lat, np.ones(lon.size))
    else:
        raise ValueError(
            f'Unexpected ocean background mode {mode!r}. Valid options are '
            'constant and rrs_latitude. Mesh-specific ocean backgrounds '
            'belong in a unified mesh family implementation.'
        )

    return values.astype(float)
