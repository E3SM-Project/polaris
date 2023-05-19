import numpy as np


class ExactSolution():

    def __init__(self, ds, eta0, nx, ny, lx, ly):

        self.f0 = ds.fVertex.mean()
        self.b0 = ds.bottomDepth.mean()
        self.angleEdge = ds.angleEdge
        self.xCell = ds.xCell
        self.yCell = ds.yCell
        self.xEdge = ds.xEdge
        self.yEdge = ds.yEdge

        self.g = 9.80616
        self.eta0 = eta0
        self.kx = nx * 2.0 * np.pi / (lx * 1e3)
        self.ky = ny * 2.0 * np.pi / (ly * 1e3)
        self.omega = np.sqrt(self.f0**2 +
                             self.g * self.b0 * (self.kx**2 + self.ky**2))

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
