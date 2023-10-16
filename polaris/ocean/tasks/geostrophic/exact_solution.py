import numpy as np
import xarray as xr
from mpas_tools.cime.constants import constants


def compute_exact_solution(alpha, vel_period, gh_0, mesh_filename):
    """
    Run this step of the testcase
    """
    a = constants['SHR_CONST_REARTH']
    g = constants['SHR_CONST_G']
    omega = 2 * np.pi / constants['SHR_CONST_SDAY']
    sec_per_day = constants['SHR_CONST_CDAY']

    u_0 = 2 * np.pi * a / (vel_period * sec_per_day)
    h_0 = gh_0 / g

    ds_mesh = xr.open_dataset(mesh_filename)
    angleEdge = ds_mesh.angleEdge
    latCell = ds_mesh.latCell
    lonCell = ds_mesh.lonCell
    latEdge = ds_mesh.latEdge
    lonEdge = ds_mesh.lonEdge

    h = _compute_h(lonCell, latCell, h_0, g, a, omega, u_0, alpha)

    u, v = _compute_u_v(lonEdge, latEdge, u_0, alpha)
    u_cell, v_cell = _compute_u_v(lonCell, latCell, u_0, alpha)

    normalVelocity = (u * np.cos(angleEdge) + v * np.sin(angleEdge))

    return h, u_cell, v_cell, normalVelocity


def _compute_h(lon, lat, h_0, g, a, omega, u_0, alpha):
    h = (h_0 - 1 / g * (a * omega * u_0 + u_0 ** 2 / 2) *
         (-np.cos(lon) * np.cos(lat) * np.sin(alpha) +
          np.sin(lat) * np.cos(alpha)) ** 2)
    return h


def _compute_u_v(lon, lat, u_0, alpha):
    u = u_0 * (np.cos(lat) * np.cos(alpha) +
               np.cos(lon) * np.sin(lat) * np.sin(alpha))
    v = -u_0 * np.sin(lon) * np.sin(alpha)
    return u, v
