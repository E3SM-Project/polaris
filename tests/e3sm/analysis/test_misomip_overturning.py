import numpy as np
import pytest
import xarray as xr
from mpas_tools.planar_hex import make_planar_hex_mesh

from polaris.ocean.overturning import (
    compute_line_interfaces,
    compute_overturning_from_edge_transport,
    get_line_edges,
)
from polaris.tasks.e3sm.analysis.misomip.diagnostics import (
    _overturning,
    isomip_mesh,
)

DC = 1000.0


@pytest.fixture(scope='module')
def ds_init():
    """A channel closed in x, as an initial condition in the protocol's
    coordinates, 60 m deep"""
    ds = make_planar_hex_mesh(
        nx=8, ny=6, dc=DC, nonperiodic_x=False, nonperiodic_y=False
    )
    x_period = ds.attrs['x_period']
    cells_on_edge = ds.cellsOnEdge.values.copy()
    x_cell = ds.xCell.values
    x1 = x_cell[cells_on_edge[:, 0] - 1]
    x2 = x_cell[cells_on_edge[:, 1] - 1]
    cells_on_edge[np.abs(x2 - x1) > 0.5 * x_period, 1] = 0
    ds['cellsOnEdge'] = (ds.cellsOnEdge.dims, cells_on_edge)
    ds.attrs['x_period'] = 0.0
    for location in ['Cell', 'Vertex']:
        for coord in ['x', 'y']:
            ds[f'{coord}Isomip{location}'] = ds[f'{coord}{location}']
    ds['bottomDepth'] = xr.ones_like(ds.xCell) * 60.0
    return ds


def _month(ds_init, with_flux):
    """A month of means whose layer thickness flux differs from the
    product of its mean velocity and thickness"""
    rng = np.random.default_rng(seed=5)
    n_edges = ds_init.sizes['nEdges']
    ds = xr.Dataset()
    ds['normalVelocity'] = (
        ('Time', 'nEdges', 'nVertLevels'),
        rng.normal(size=(1, n_edges, 3)),
    )
    if with_flux:
        ds['normalLayerThicknessFlux'] = (
            ('Time', 'nEdges', 'nVertLevels'),
            rng.normal(size=(1, n_edges, 3)),
        )
    ds['layerThickness'] = (
        xr.ones_like(ds_init.xCell)
        * xr.DataArray([10.0, 20.0, 30.0], dims='nVertLevels')
    ).expand_dims(Time=1)
    ds['ssh'] = xr.zeros_like(ds_init.xCell).expand_dims(Time=1)
    return ds


def test_the_overturning_takes_the_layer_thickness_flux(ds_init):
    ds = _month(ds_init, with_flux=True)

    osf = _overturning(ds, ds_init, DC, 5.0)

    assert osf.attrs['method'] == 'normalLayerThicknessFlux'
    x_line = float(osf.x.values[2]) * 1e3
    line = get_line_edges(isomip_mesh(ds_init), 'x', x_line)
    month = ds.isel(Time=0)
    transport = (
        month.normalLayerThicknessFlux.isel(nEdges=line.edgeIndex)
        * line.sign
        * line.dvEdge
    )
    z_top, z_bottom = compute_line_interfaces(
        line, month.ssh, month.layerThickness
    )
    expected = compute_overturning_from_edge_transport(
        transport, z_top, z_bottom, osf.zInterface.values
    )
    np.testing.assert_allclose(
        osf.isel(Time=0, x=2).values, 1e-6 * expected.values
    )


def test_without_the_flux_the_overturning_takes_the_monthly_means(ds_init):
    osf = _overturning(_month(ds_init, with_flux=False), ds_init, DC, 5.0)
    assert osf.attrs['method'] == 'monthly means of velocity and thickness'
