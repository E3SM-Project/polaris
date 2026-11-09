"""
The balanced jet and height perturbation of Galewsky, Scott & Polvani
(2004), Tellus A 56(5), 429-440, https://doi.org/10.3402/tellusa.v56i5.14436
"""

import numpy as np
from scipy.integrate import cumulative_trapezoid

from polaris.constants import get_constant

# the number of latitudes on the pole-to-pole grid used for quadrature
QUADRATURE_POINTS = 100001


def get_jet_params(config):
    """
    Read the jet and perturbation parameters from the ``galewsky_jet``
    config section

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Config options with a ``galewsky_jet`` section

    Returns
    -------
    params : dict
        The jet parameters (``u_max``, ``phi0``, ``phi1``, ``h_mean``) and
        perturbation parameters (``h_hat``, ``alpha``, ``beta``, ``phi2``),
        with angles in radians
    """
    section = config['galewsky_jet']
    phi0 = np.deg2rad(section.getfloat('jet_south_lat'))
    phi1 = np.deg2rad(section.getfloat('jet_north_lat'))
    params = dict(
        u_max=section.getfloat('u_max'),
        phi0=phi0,
        phi1=phi1,
        h_mean=section.getfloat('h_mean'),
        h_hat=section.getfloat('perturbation_amplitude'),
        alpha=section.getfloat('perturbation_lon_width'),
        beta=section.getfloat('perturbation_lat_width'),
        phi2=np.deg2rad(section.getfloat('perturbation_lat')),
    )
    return params


def jet_velocity(lat, u_max, phi0, phi1):
    """
    The zonal velocity of the jet (GSP04 eq. 2)

    Parameters
    ----------
    lat : numpy.ndarray
        Latitude in radians

    u_max : float
        The peak velocity in m/s

    phi0 : float
        The latitude of the jet's southern edge in radians

    phi1 : float
        The latitude of the jet's northern edge in radians

    Returns
    -------
    u : numpy.ndarray
        The zonal velocity in m/s, zero outside the jet
    """
    lat = np.asarray(lat, dtype=float)
    u = np.zeros_like(lat)
    en = np.exp(-4.0 / (phi1 - phi0) ** 2)
    jet = (lat > phi0) & (lat < phi1)
    u[jet] = u_max / en * np.exp(1.0 / ((lat[jet] - phi0) * (lat[jet] - phi1)))
    return u


def balanced_height(lat, u_max, phi0, phi1, h_mean):
    """
    The height in gradient-wind balance with the jet (GSP04 eq. 3), shifted
    so that its area-weighted global mean is ``h_mean``

    Parameters
    ----------
    lat : numpy.ndarray
        Latitude in radians

    u_max : float
        The peak velocity in m/s

    phi0 : float
        The latitude of the jet's southern edge in radians

    phi1 : float
        The latitude of the jet's northern edge in radians

    h_mean : float
        The global mean of the height in m

    Returns
    -------
    h : numpy.ndarray
        The height in m
    """
    radius = get_constant('mean_radius')
    gravity = get_constant('standard_acceleration_of_gravity')
    omega = get_constant('angular_velocity')

    phi = _quadrature_lat()
    u = jet_velocity(phi, u_max, phi0, phi1)
    coriolis = 2.0 * omega * np.sin(phi)
    # the jet is zero at the poles, where tan(phi) is infinite
    jet = u != 0.0
    integrand = np.zeros_like(phi)
    integrand[jet] = (
        radius * u[jet] * (coriolis[jet] + np.tan(phi[jet]) / radius * u[jet])
    )
    h = -cumulative_trapezoid(integrand, phi, initial=0.0) / gravity

    weight = np.cos(phi)
    h_ave = np.trapezoid(h * weight, phi) / np.trapezoid(weight, phi)
    h = h - h_ave + h_mean
    return np.interp(np.asarray(lat, dtype=float), phi, h)


def streamfunction(lat, u_max, phi0, phi1):
    """
    The streamfunction of the jet, psi = -a int u dphi, so that the zonal
    velocity is -(1/a) dpsi/dphi

    Parameters
    ----------
    lat : numpy.ndarray
        Latitude in radians

    u_max : float
        The peak velocity in m/s

    phi0 : float
        The latitude of the jet's southern edge in radians

    phi1 : float
        The latitude of the jet's northern edge in radians

    Returns
    -------
    psi : numpy.ndarray
        The streamfunction in m^2/s
    """
    radius = get_constant('mean_radius')
    phi = _quadrature_lat()
    u = jet_velocity(phi, u_max, phi0, phi1)
    psi = -radius * cumulative_trapezoid(u, phi, initial=0.0)
    return np.interp(np.asarray(lat, dtype=float), phi, psi)


def height_perturbation(lon, lat, h_hat, alpha, beta, phi2):
    """
    The height perturbation that triggers the instability (GSP04 eq. 4),
    centred at longitude zero

    Parameters
    ----------
    lon : numpy.ndarray
        Longitude in radians

    lat : numpy.ndarray
        Latitude in radians

    h_hat : float
        The amplitude in m

    alpha : float
        The longitudinal width in radians

    beta : float
        The latitudinal width in radians

    phi2 : float
        The latitude of the centre in radians

    Returns
    -------
    h_prime : numpy.ndarray
        The height perturbation in m
    """
    # wrap longitude into [-pi, pi)
    lon = np.mod(np.asarray(lon, dtype=float) + np.pi, 2.0 * np.pi) - np.pi
    lat = np.asarray(lat, dtype=float)
    return (
        h_hat
        * np.cos(lat)
        * np.exp(-((lon / alpha) ** 2))
        * np.exp(-(((phi2 - lat) / beta) ** 2))
    )


def normal_velocity_from_streamfunction(ds_mesh, psi_vertex):
    """
    Compute the normal velocity on edges as the difference of a
    streamfunction between each edge's two vertices.  The discrete
    divergence of the result is zero to round-off.

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        An MPAS spherical mesh

    psi_vertex : numpy.ndarray
        The streamfunction at vertices in m^2/s

    Returns
    -------
    normal_velocity : numpy.ndarray
        The normal velocity on edges in m/s
    """
    cells_on_edge = ds_mesh.cellsOnEdge.values - 1
    vertices_on_edge = ds_mesh.verticesOnEdge.values - 1
    x_cell = _positions(ds_mesh, 'Cell')
    x_vertex = _positions(ds_mesh, 'Vertex')
    x_edge = _positions(ds_mesh, 'Edge')

    cell0 = cells_on_edge[:, 0]
    cell1 = cells_on_edge[:, 1]
    vertex0 = vertices_on_edge[:, 0]
    vertex1 = vertices_on_edge[:, 1]
    normal = x_cell[cell1] - x_cell[cell0]
    tangent = x_vertex[vertex1] - x_vertex[vertex0]
    k_hat = x_edge / np.linalg.norm(x_edge, axis=1, keepdims=True)
    # +1 where the second vertex lies in the direction k x n from the first
    sign = np.sign(np.sum(np.cross(k_hat, normal) * tangent, axis=1))

    dpsi = psi_vertex[vertex1] - psi_vertex[vertex0]
    # u = k x grad(psi), so u . n = -grad(psi) . (k x n)
    return -sign * dpsi / ds_mesh.dvEdge.values


def _quadrature_lat():
    """
    A fine pole-to-pole latitude grid for quadrature
    """
    return np.linspace(-0.5 * np.pi, 0.5 * np.pi, QUADRATURE_POINTS)


def _positions(ds_mesh, location):
    """
    Cartesian positions of cells, edges or vertices as an (n, 3) array
    """
    return np.stack(
        [
            ds_mesh[f'x{location}'].values,
            ds_mesh[f'y{location}'].values,
            ds_mesh[f'z{location}'].values,
        ],
        axis=1,
    )
