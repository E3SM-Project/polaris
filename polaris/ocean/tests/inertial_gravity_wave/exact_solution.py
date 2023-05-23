import numpy as np


class ExactSolution():

    def __init__(self, ds, config):

        bottom_depth = config.getfloat('vertical_grid', 'bottom_depth')
        self.angleEdge = ds.angleEdge
        self.xCell = ds.xCell
        self.yCell = ds.yCell
        self.xEdge = ds.xEdge
        self.yEdge = ds.yEdge

        section = config['inertial_gravity_wave']
        self.g = 9.80616
        self.f0 = section.getfloat('f0')
        self.eta0 = section.getfloat('eta0')
        lx = section.getfloat('lx')
        ly = np.sqrt(3.0) / 2.0 * lx
        npx = section.getfloat('nx')  # rename these
        npy = section.getfloat('ny')
        self.kx = npx * 2.0 * np.pi / (lx * 1e3)
        self.ky = npy * 2.0 * np.pi / (ly * 1e3)
        self.omega = np.sqrt(self.f0**2 +
                             self.g * bottom_depth * (self.kx**2 + self.ky**2))

    def ssh(self, t):

        eta = self.eta0 * np.cos(self.kx * self.xCell +
                                 self.ky * self.yCell -
                                 self.omega * t)

        return eta

    def normalVelocity(self, t):

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

        return u * np.cos(self.angleEdge) + v * np.sin(self.angleEdge)
