import numpy as np

from polaris.mesh import QuasiUniformSphericalMeshStep
from polaris.mesh.base.so.background import build_southern_ocean_background


class SOBaseMesh(QuasiUniformSphericalMeshStep):
    """
    A step for creating Southern Ocean (SO) regionally refined meshes
    """

    def setup(self):
        """
        Add some input files
        """

        self.add_input_file(
            filename='high_res_region.geojson',
            package='polaris.mesh.base.so',
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
        nlon = int(360.0 / dlon) + 1
        nlat = int(180.0 / dlat) + 1
        lon = np.linspace(-180.0, 180.0, nlon)
        lat = np.linspace(-90.0, 90.0, nlat)

        cell_width = build_southern_ocean_background(
            lat=lat,
            lon=lon,
            high_res_km=min_res,
            low_res_km=max_res,
            region_filename='high_res_region.geojson',
        )

        return cell_width, lon, lat
