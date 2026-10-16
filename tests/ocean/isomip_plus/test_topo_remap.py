import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf
from numpy.testing import assert_allclose

from polaris.tasks.ocean.isomip_plus.topo.remap import TopoRemap


def test_renormalize_keeps_ocean_fraction(tmp_path, monkeypatch):
    """Fields are renormalized by the ocean fraction, but the ocean
    fraction itself is kept so the mesh cull can compare it with
    min_ocean_fraction"""
    monkeypatch.chdir(tmp_path)
    ocean_frac = np.array([1.0, 0.4, 0.0])
    ds = xr.Dataset()
    ds['oceanFraction'] = ('nCells', ocean_frac)
    ds['bedrockTopography'] = ('nCells', -500.0 * ocean_frac)
    ds['bedrockTopography'].attrs['units'] = 'm'
    write_netcdf(ds, 'topography_rename.nc')

    TopoRemap._renormalize()

    with xr.open_dataset('topography_remapped.nc') as ds_out:
        assert_allclose(ds_out.oceanFraction.values, ocean_frac)
        assert_allclose(
            ds_out.bedrockTopography.values, [-500.0, -500.0, np.nan]
        )
        assert ds_out.bedrockTopography.attrs['units'] == 'm'
