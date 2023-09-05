import numpy as np


class ExactSolution():
    """
    Class to compute the exact solution for the manufactured solution
    test case

    Attributes
    ----------
    angleEdge : xr.DataArray
        angle between edge normals and positive x direction

    xCell : xr.DataArray
        x coordinates of mesh cell centers

    yCell : xr.DataArray
        y coordinates of mesh cell centers

    xEdge: xr.DataArray
        x coordinates of mesh edges

    yEdge : xr.DataArray
        y coordinates of mesh edges

    eta0 : float
        Amplitide of sea surface height

    kx : float
        Wave number in the x direction

    ky : float
        Wave number in the y direction

    omega : float
        Angular frequency
    """

    def __init__(self, config, ds=None):
        """
        Create a new exact solution object

        Parameters
        ----------
        ds : xr.DataSet
            MPAS mesh information

        config : polaris.config.PolarisConfigParser
            Config options for test case
        """
        bottom_depth = config.getfloat('vertical_grid', 'bottom_depth')
        section = config['manufactured_solution']
        self.g = 9.80616
        self.eta0 = section.getfloat('ssh_amplitude')
        lx = section.getfloat('lx')
        ly = np.sqrt(3.0) / 2.0 * lx
        npx = section.getfloat('n_wavelengths_x')
        npy = section.getfloat('n_wavelengths_y')
        self.lambda_x = (lx * 1e3) / npx
        self.lambda_y = (ly * 1e3) / npy
        self.kx = 2.0 * np.pi / self.lambda_x
        self.ky = 2.0 * np.pi / self.lambda_y
        self.omega = np.sqrt(self.g * bottom_depth *
                             (self.kx**2 + self.ky**2))

        if ds is not None:
            self.angleEdge = ds.angleEdge
            self.xCell = ds.xCell
            self.yCell = ds.yCell
            self.xEdge = ds.xEdge
            self.yEdge = ds.yEdge

    def ssh(self, t):
        """
        Exact solution for sea surface height

        Parameters
        ----------
        t : float
            time at which to evaluate exact solution

        Returns
        -------
        eta : xr.DataArray
            the exact sea surface height solution on cells at time t

        """

        eta = self.eta0 * np.sin(self.kx * self.xCell +
                                 self.ky * self.yCell -
                                 self.omega * t)

        return eta

    def normal_velocity(self, t):
        """
        Exact solution for normal velocity

        Parameters
        ----------
        t : float
            time at which to evaluate exact solution

        Returns
        -------
        normalvelocity : xr.DataArray
            the exact normal velocity solution on edges at time t
        """
        u = self.eta0 * np.cos(self.kx * self.xEdge +
                               self.ky * self.yEdge -
                               self.omega * t)
        v = u
        return u * np.cos(self.angleEdge) + v * np.sin(self.angleEdge)
