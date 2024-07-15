import re

import mpas_tools.mesh.creation.mesh_definition_tools as mdt
import numpy as np

from polaris.mesh.spherical import QuasiUniformSphericalMeshStep


class RRSBaseMesh(QuasiUniformSphericalMeshStep):
    """
    A step for creating RRS (Rossby-radius scaled) meshes

    Attributes
    ----------
    cell_width_pole : float
        The resolution at the poles in km

    cell_width_eq : float
        The resolution at the equator in km
    """

    def __init__(self, component, resolutions, name='base_mesh', subdir=None):
        """
        Create a new step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        resolutions : str
            The range of resolutions (e.g. '6to18km')

        name : str, optional
            the name of the step

        subdir : {str, None}, optional
            the subdirectory for the step

        """
        super().__init__(component=component, name=name, subdir=subdir)

        m = re.match(r'(.*)to(.*)km', resolutions)
        if m is None:
            raise ValueError('resolutions does not appear to be of the form '
                             '"XXtoXXkm" as expected.')
        try:
            self.cell_width_pole = float(m.group(1))
            self.cell_width_eq = float(m.group(2))
        except ValueError:
            # failed to convert
            raise ValueError('resolutions does not appear to be of the form '
                             '"XXtoXXkm" as expected.')

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

        dlon = 10.
        dlat = 0.1
        nlon = int(360. / dlon) + 1
        nlat = int(180. / dlat) + 1
        lon = np.linspace(-180., 180., nlon)
        lat = np.linspace(-90., 90., nlat)

        cellWidthVsLat = mdt.RRS_CellWidthVsLat(
            lat, cellWidthEq=self.cell_width_eq,
            cellWidthPole=self.cell_width_pole)
        cellWidth = np.outer(cellWidthVsLat, np.ones([1, lon.size]))

        return cellWidth, lon, lat
