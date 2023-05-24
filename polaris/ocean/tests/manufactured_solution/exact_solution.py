import numpy as np


class ExactSolution():

    def __init__(self, config, ds=None):

        bottom_depth = config.getfloat('vertical_grid', 'bottom_depth')
        section = config['manufactured_solution']
        self.g = 9.80616
        self.eta0 = section.getfloat('eta0')
        lx = section.getfloat('lx')
        ly = np.sqrt(3.0) / 2.0 * lx
        npx = section.getfloat('npx')
        npy = section.getfloat('npy')
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
