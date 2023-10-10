import numpy as np
from mpas_tools.cime.constants import constants


class ExactSolution():
    """
    Class to compute the exact solution for the inertial gravity wave
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

    f0 : float
        Coriolis parameter

    eta0 : float
        Amplitide of sea surface height

    kx : float
        Wave number in the x direction

    ky : float
        Wave number in the y direction

    omega : float
        Angular frequency
    """
    def __init__(self, ds, config):
        """
        Create a new exact solution object

        Parameters
        ----------
        ds : xr.DataSet
            MPAS mesh information

        config : polaris.config.PolarisConfigParser
            Config options for test case
        """
        self.angleEdge = ds.angleEdge
        self.xCell = ds.xCell
        self.yCell = ds.yCell
        self.xEdge = ds.xEdge
        self.yEdge = ds.yEdge

        bottom_depth = config.getfloat('vertical_grid', 'bottom_depth')
        section = config['inertial_gravity_wave']
        self.f0 = section.getfloat('coriolis_parameter')
        self.eta0 = section.getfloat('ssh_amplitude')
        lx = section.getfloat('lx')
        npx = section.getfloat('n_wavelengths_x')
        npy = section.getfloat('n_wavelengths_y')

        self.g = constants['SHR_CONST_G']
        ly = np.sqrt(3.0) / 2.0 * lx
        self.kx = npx * 2.0 * np.pi / (lx * 1e3)
        self.ky = npy * 2.0 * np.pi / (ly * 1e3)
        self.omega = np.sqrt(self.f0**2 +
                             self.g * bottom_depth * (self.kx**2 + self.ky**2))

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
        eta = self.eta0 * np.cos(self.kx * self.xCell +
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
        norm_vel : xr.DataArray
            the exact normal velocity solution on edges at time t
        """
        u = self.eta0 * (self.g / (self.omega**2.0 - self.f0**2.0) *
                         (self.omega * self.kx * np.cos(self.kx * self.xEdge +
                          self.ky * self.yEdge - self.omega * t) -
                          self.f0 * self.ky * np.sin(self.kx * self.xEdge +
                          self.ky * self.yEdge - self.omega * t)))

        v = self.eta0 * (self.g / (self.omega**2.0 - self.f0**2.0) *
                         (self.omega * self.ky * np.cos(self.kx * self.xEdge +
                          self.ky * self.yEdge - self.omega * t) +
                          self.f0 * self.kx * np.sin(self.kx * self.xEdge +
                          self.ky * self.yEdge - self.omega * t)))

        norm_vel = u * np.cos(self.angleEdge) + v * np.sin(self.angleEdge)

        return norm_vel
