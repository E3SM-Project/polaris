import mpas_tools.mesh.creation.mesh_definition_tools as mdt
import numpy as np

from polaris.mesh import QuasiUniformSphericalMeshStep


class RRSBaseMesh(QuasiUniformSphericalMeshStep):
    """
    A step for creating Rossby Radius Scaled (RRS) variable resolution meshes
    """

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

        dlon = 10.0
        dlat = 0.1
        nlon = int(360.0 / dlon) + 1
        nlat = int(180.0 / dlat) + 1
        lon = np.linspace(-180.0, 180.0, nlon)
        lat = np.linspace(-90.0, 90.0, nlat)

        cell_width_vs_lat = mdt.RRS_CellWidthVsLat(
            lat, cellWidthEq=max_res, cellWidthPole=min_res
        )
        cell_width = np.outer(cell_width_vs_lat, np.ones([1, lon.size]))

        return cell_width, lon, lat
