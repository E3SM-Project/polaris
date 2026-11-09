from __future__ import annotations

from typing import TYPE_CHECKING

from polaris.config import PolarisConfigParser
from polaris.lazy import lazy_module

if TYPE_CHECKING:
    import numpy as np
    import xarray as xr
else:
    np = lazy_module('numpy')
    xr = lazy_module('xarray')


def surface_pressure_from_config(
    config: PolarisConfigParser, n_cells: int
) -> xr.DataArray:
    """
    Construct a spatially uniform surface pressure field from the
    ``vertical_grid:surface_pressure`` config option.

    Omega requires a surface pressure in its initial state, whereas
    MPAS-Ocean does not.  Tasks that prescribe their own (spatially
    varying) surface pressure should do so directly rather than calling
    this function.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Configuration options, including ``vertical_grid:surface_pressure``

    n_cells : int
        The number of cells in the mesh

    Returns
    -------
    surface_pressure : xarray.DataArray
        A uniform surface pressure field with dimension ``nCells``
    """
    surface_pressure = config.getfloat('vertical_grid', 'surface_pressure')
    return xr.DataArray(
        data=surface_pressure * np.ones(n_cells, dtype=float),
        dims=('nCells',),
        attrs={'units': 'Pa', 'long_name': 'sea surface pressure'},
    )
