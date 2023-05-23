import numpy as np


class ExactSolution():

    def __init__(self, ds, config):

        bottom_depth = config.getfloat('vertical_grid', 'bottom_depth')
        self.angleEdge = ds.angleEdge
        self.xCell = ds.xCell
        self.yCell = ds.yCell
        self.xEdge = ds.xEdge
        self.yEdge = ds.yEdge

        section = config['manufactured_solution']
        self.g = 9.80616
        self.eta0 = section.getfloat('eta0')
        lx = section.getfloat('lx')
        ly = np.sqrt(3.0) / 2.0 * lx
        npx = section.getfloat('npx')
        npy = section.getfloat('npy')
        self.kx = npx * 2.0 * np.pi / (lx * 1e3)
        self.ky = npy * 2.0 * np.pi / (ly * 1e3)
        self.omega = np.sqrt(self.g * bottom_depth *
                             (self.kx**2 + self.ky**2))

    def ssh(self, t):

        eta = self.eta0 * np.sin(self.kx * self.xCell +
                                 self.ky * self.yCell -
                                 self.omega * t)

        return eta

    def normalVelocity(self, t):

        u = self.eta0 * np.cos(self.kx * self.xEdge +
                               self.ky * self.yEdge -
                               self.omega * t)
        v = 0.0
        return u * np.cos(self.angleEdge) + v * np.sin(self.angleEdge)
