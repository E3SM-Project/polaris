import xarray as xr

from polaris.constants import get_constant
from polaris.mesh.info import is_spherical
from polaris.mesh.variables import get_mesh_variables


def rescale_sphere_radius(
    ds: xr.Dataset, radius: float | None = None
) -> list[str]:
    """
    Rescale the coordinates, lengths and areas of a spherical MPAS mesh to a
    new sphere radius, in place, and update the ``sphere_radius`` global
    attribute to match.  Latitudes, longitudes, angles and dimensionless
    fields are unchanged.  The variables rescaled are the
    ``length_variables`` and ``area_variables`` groups from
    :py:func:`polaris.mesh.variables.get_mesh_variables`.  Those not in
    ``ds`` are skipped, so the function works on any MPAS component's mesh,
    initial-condition or restart file.

    Parameters
    ----------
    ds : xarray.Dataset
        A dataset on a spherical MPAS mesh with a positive ``sphere_radius``
        global attribute.  The variables are replaced with rescaled copies
        that keep their attributes and encoding.

    radius : float, optional
        The new sphere radius in meters.  The default is the PCD's
        ``mean_radius``.

    Returns
    -------
    rescaled : list of str
        The names of the variables that were rescaled

    Raises
    ------
    ValueError
        If the mesh is not spherical or ``sphere_radius`` is missing or not
        positive
    """
    if not is_spherical(ds):
        raise ValueError(
            "Only meshes with on_a_sphere = 'YES' can be rescaled to a new "
            'sphere radius.'
        )
    if 'sphere_radius' not in ds.attrs:
        raise ValueError(
            'The global attribute sphere_radius is required to rescale a '
            'spherical mesh.'
        )
    sphere_radius = float(ds.attrs['sphere_radius'])
    if sphere_radius <= 0.0:
        raise ValueError(f'Invalid sphere_radius: {sphere_radius}')

    if radius is None:
        radius = float(get_constant('mean_radius'))

    rescaled = []
    for name in get_mesh_variables('length_variables'):
        if name in ds:
            values = radius * ds[name].values / sphere_radius
            ds[name] = ds[name].copy(data=values)
            rescaled.append(name)

    for name in get_mesh_variables('area_variables'):
        if name in ds:
            values = (
                radius
                * radius
                * ds[name].values
                / (sphere_radius * sphere_radius)
            )
            ds[name] = ds[name].copy(data=values)
            rescaled.append(name)

    ds.attrs['sphere_radius'] = radius
    return rescaled
