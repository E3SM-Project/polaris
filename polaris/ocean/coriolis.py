import numpy as np
import xarray as xr

from polaris.config import PolarisConfigParser
from polaris.constants import get_constant


def add_coriolis_to_dataset(
    config: PolarisConfigParser, ds_mesh: xr.Dataset
) -> xr.Dataset:
    """
    Add Coriolis fields to a mesh dataset based on the ``type`` option
    in the ``[coriolis]`` config section.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Configuration object containing ocean parameters.

    ds_mesh : xarray.Dataset
        The horizontal mesh dataset to update.

    Returns
    -------
    xarray.Dataset
        The updated dataset with ``fCell``, ``fEdge``, and ``fVertex``
        fields.
    """
    section = config['coriolis']
    coriolis_type = section.get('type').strip()
    if coriolis_type == 'zero':
        return add_zero_coriolis(ds_mesh)
    elif coriolis_type == 'constant':
        f = section.getfloat('constant_f')
        return add_constant_coriolis(ds_mesh, f)
    elif coriolis_type == 'beta_plane':
        f0 = section.getfloat('beta_plane_f0')
        beta = section.getfloat('beta_plane_beta')
        return add_beta_plane_coriolis(ds_mesh, f0, beta)
    elif coriolis_type == 'spherical':
        return add_spherical_coriolis(ds_mesh)
    elif coriolis_type == 'rotated_sphere':
        alpha = section.getfloat('rotated_sphere_alpha')
        return add_rotated_sphere_coriolis(ds_mesh, alpha)
    else:
        raise ValueError(f'Unsupported Coriolis type: {coriolis_type}')


def add_beta_plane_coriolis(
    ds_mesh: xr.Dataset, f0: float, beta: float
) -> xr.Dataset:
    """
    Add beta-plane Coriolis fields to a horizontal mesh dataset.

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        The horizontal mesh dataset to update in place

    f0 : float
        The Coriolis parameter at ``y=0``

    beta : float
        The meridional gradient of the Coriolis parameter

    Returns
    -------
    xarray.Dataset
        The updated dataset
    """
    return _set_coriolis_fields(
        ds_mesh,
        f0 + beta * ds_mesh.yCell,
        f0 + beta * ds_mesh.yEdge,
        f0 + beta * ds_mesh.yVertex,
    )


def add_constant_coriolis(
    ds_mesh: xr.Dataset, coriolis_parameter: float
) -> xr.Dataset:
    """
    Add constant Coriolis fields to a horizontal mesh dataset.

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        The horizontal mesh dataset to update in place

    coriolis_parameter : float
        The constant Coriolis parameter value

    Returns
    -------
    xarray.Dataset
        The updated dataset
    """
    return _set_coriolis_fields(
        ds_mesh,
        coriolis_parameter * xr.ones_like(ds_mesh.xCell),
        coriolis_parameter * xr.ones_like(ds_mesh.xEdge),
        coriolis_parameter * xr.ones_like(ds_mesh.xVertex),
    )


def add_rotated_sphere_coriolis(
    ds_mesh: xr.Dataset, alpha: float, omega: float | None = None
) -> xr.Dataset:
    """
    Add Coriolis fields for a sphere rotated by angle ``alpha``.

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        The horizontal mesh dataset to update in place

    alpha : float
        The rotation angle in radians

    omega : float, optional
        The angular rotation rate. If not provided, the Earth's angular
        velocity is used.

    Returns
    -------
    xarray.Dataset
        The updated dataset
    """
    if omega is None:
        omega = get_constant('angular_velocity')

    return _set_coriolis_fields(
        ds_mesh,
        _rotated_sphere_coriolis(
            ds_mesh.lonCell, ds_mesh.latCell, alpha, omega
        ),
        _rotated_sphere_coriolis(
            ds_mesh.lonEdge, ds_mesh.latEdge, alpha, omega
        ),
        _rotated_sphere_coriolis(
            ds_mesh.lonVertex, ds_mesh.latVertex, alpha, omega
        ),
    )


def add_spherical_coriolis(
    ds_mesh: xr.Dataset, omega: float | None = None
) -> xr.Dataset:
    """
    Add Coriolis fields for the Earth's rotation axis.

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        The horizontal mesh dataset to update in place

    omega : float, optional
        The angular rotation rate. If not provided, the Earth's angular
        velocity is used.

    Returns
    -------
    xarray.Dataset
        The updated dataset
    """
    return add_rotated_sphere_coriolis(ds_mesh, alpha=0.0, omega=omega)


def add_zero_coriolis(ds_mesh: xr.Dataset) -> xr.Dataset:
    """
    Add zero-valued Coriolis fields to a horizontal mesh dataset.

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        The horizontal mesh dataset to update in place

    Returns
    -------
    xarray.Dataset
        The updated dataset
    """
    return _set_coriolis_fields(
        ds_mesh,
        xr.zeros_like(ds_mesh.xCell),
        xr.zeros_like(ds_mesh.xEdge),
        xr.zeros_like(ds_mesh.xVertex),
    )


def _rotated_sphere_coriolis(
    lon: xr.DataArray, lat: xr.DataArray, alpha: float, omega: float
) -> xr.DataArray:
    return (
        2.0
        * omega
        * (
            -np.cos(lon) * np.cos(lat) * np.sin(alpha)
            + np.sin(lat) * np.cos(alpha)
        )
    )


def _set_coriolis_fields(
    ds_mesh: xr.Dataset,
    f_cell: xr.DataArray,
    f_edge: xr.DataArray,
    f_vertex: xr.DataArray,
) -> xr.Dataset:
    ds_mesh['fCell'] = _add_coriolis_attrs(f_cell, 'cell centers')
    ds_mesh['fEdge'] = _add_coriolis_attrs(f_edge, 'edges')
    ds_mesh['fVertex'] = _add_coriolis_attrs(f_vertex, 'vertices')
    return ds_mesh


def _add_coriolis_attrs(
    data_array: xr.DataArray, location: str
) -> xr.DataArray:
    data_array.attrs.update(
        {
            'long_name': f'Coriolis parameter at {location}',
            'standard_name': 'coriolis_parameter',
            'units': 'radians s^-1',
        }
    )
    return data_array
