import numpy as np
from geometric_features import read_feature_collection
from mpas_tools.cime.constants import constants
from mpas_tools.mesh.creation.signed_distance import (
    signed_distance_from_geojson,
)

from polaris.mesh import QuasiUniformSphericalMeshStep


class SOBaseMesh(QuasiUniformSphericalMeshStep):
    """
    A step for creating Southern Ocean (SO) regionally refined meshes
    """

    def setup(self):
        """
        Add some input files
        """

        self.add_input_file(
            filename='high_res_region.geojson', package=self.__module__
        )

        super().setup()

    def build_cell_width_lat_lon(self):
        """
        Create cell width array for this mesh on a regular latitude-longitude
        grid

        Returns
        -------
        cellWidth : numpy.array
            m x n array of cell width in km

        lon : numpy.array
            longitude in degrees (length n and between -180 and 180)

        lat : numpy.array
            longitude in degrees (length m and between -90 and 90)
        """
        config = self.config
        section = config['spherical_mesh']
        min_res = section.getfloat('min_cell_width')
        max_res = section.getfloat('max_cell_width')

        dlon = 0.1
        dlat = dlon
        earth_radius = constants['SHR_CONST_REARTH']
        nlon = int(360.0 / dlon) + 1
        nlat = int(180.0 / dlat) + 1
        lon = np.linspace(-180.0, 180.0, nlon)
        lat = np.linspace(-90.0, 90.0, nlat)

        # start with a uniform max_res km background resolution
        cell_width = max_res * np.ones((nlat, nlon))

        fc = read_feature_collection('high_res_region.geojson')

        so_signed_distance = signed_distance_from_geojson(
            fc, lon, lat, earth_radius, max_length=0.25
        )

        # Equivalent to 20 degrees latitude
        trans_width = 1600e3
        trans_start = 500e3

        weights = 0.5 * (
            1 + np.tanh((so_signed_distance - trans_start) / trans_width)
        )

        cell_width = min_res * (1 - weights) + cell_width * weights

        return cell_width, lon, lat
