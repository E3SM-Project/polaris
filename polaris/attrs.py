"""
Helpers for setting metadata attributes on xarray variables.
"""

import xarray as xr

__all__ = ['set_attrs']


def set_attrs(
    da: xr.DataArray,
    long_name: str | None = None,
    units: str | None = None,
    **extra: str,
) -> xr.DataArray:
    """
    Replace the attributes of ``da`` in place with the given metadata.

    Any attributes ``da`` already has are *discarded*, not merged.  This is
    the point of the helper: xarray propagates ``attrs`` through arithmetic,
    comparisons, ``where()`` and ``zeros_like()``, so a variable computed from
    another arrives carrying its parent's metadata.  Setting individual keys
    (``da.attrs['units'] = ...``) leaves the rest of the parent's metadata
    behind, which is how level indices and masks derived from a seafloor
    pressure ended up labelled as pressures in Pascals.

    The array is modified in place and also returned, so either call pattern
    works::

        ds['minLevelCell'] = min_level_cell + 1
        set_attrs(ds.minLevelCell, long_name='Index to the first ...')

        ds['bottomDepth'] = set_attrs(
            -geom_z_bot, long_name='seafloor geometric depth', units='m'
        )

    Parameters
    ----------
    da : xarray.DataArray
        The variable to label.  Its existing attributes are discarded.

    long_name : str, optional
        The ``long_name`` attribute.  Omitted from the result if ``None``.

    units : str, optional
        The ``units`` attribute.  Omitted from the result if ``None``.  Leave
        it out for quantities with no meaningful unit, such as one-based level
        indices, rather than inventing one.

    extra : str
        Any further attributes to set, such as ``note`` or ``standard_name``.

    Returns
    -------
    xarray.DataArray
        ``da``, so the call can be used inline in an assignment.
    """
    attrs: dict[str, str] = {}
    if long_name is not None:
        attrs['long_name'] = long_name
    if units is not None:
        attrs['units'] = units
    attrs.update(extra)
    da.attrs = attrs
    return da
