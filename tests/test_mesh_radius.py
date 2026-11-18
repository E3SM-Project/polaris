"""
Unit tests for rescaling a spherical MPAS mesh to a new sphere radius.
"""

import numpy as np
import pytest
import xarray as xr

from polaris.constants import get_constant
from polaris.mesh.radius import (
    AREA_VARIABLES,
    LENGTH_VARIABLES,
    rescale_sphere_radius,
)

OLD_RADIUS = 6.0e6
NEW_RADIUS = 6.5e6


def test_rescales_lengths_and_areas():
    ds = _make_mesh()
    original = ds.copy(deep=True)

    rescaled = rescale_sphere_radius(ds, NEW_RADIUS)

    assert set(rescaled) == set(LENGTH_VARIABLES + AREA_VARIABLES)
    ratio = NEW_RADIUS / OLD_RADIUS
    for name in LENGTH_VARIABLES:
        np.testing.assert_allclose(ds[name], ratio * original[name])
    for name in AREA_VARIABLES:
        np.testing.assert_allclose(ds[name], ratio**2 * original[name])
    assert ds.attrs['sphere_radius'] == NEW_RADIUS


def test_leaves_other_fields_and_attributes_alone():
    ds = _make_mesh()
    original = ds.copy(deep=True)

    rescale_sphere_radius(ds, NEW_RADIUS)

    xr.testing.assert_identical(ds['latCell'], original['latCell'])
    xr.testing.assert_identical(
        ds['layerThickness'], original['layerThickness']
    )
    assert ds['areaCell'].attrs == original['areaCell'].attrs


def test_skips_missing_variables():
    ds = _make_mesh().drop_vars(['kiteAreasOnVertex', 'zVertex'])

    rescaled = rescale_sphere_radius(ds, NEW_RADIUS)

    assert 'kiteAreasOnVertex' not in rescaled
    assert 'zVertex' not in rescaled
    assert 'areaCell' in rescaled


def test_default_radius_is_pcd_mean_radius():
    ds = _make_mesh()

    rescale_sphere_radius(ds)

    assert ds.attrs['sphere_radius'] == get_constant('mean_radius')


def test_planar_mesh_is_an_error():
    ds = _make_mesh()
    ds.attrs['on_a_sphere'] = 'NO'

    with pytest.raises(ValueError, match='on_a_sphere'):
        rescale_sphere_radius(ds, NEW_RADIUS)


@pytest.mark.parametrize('radius', [None, 0.0])
def test_missing_or_invalid_sphere_radius_is_an_error(radius):
    ds = _make_mesh()
    if radius is None:
        del ds.attrs['sphere_radius']
    else:
        ds.attrs['sphere_radius'] = radius

    with pytest.raises(ValueError, match='sphere_radius'):
        rescale_sphere_radius(ds, NEW_RADIUS)


def _make_mesh():
    rng = np.random.default_rng(seed=0)
    sizes = {'nCells': 5, 'nEdges': 7, 'nVertices': 4}
    dims = {
        'Cell': 'nCells',
        'Edge': 'nEdges',
        'Vertex': 'nVertices',
    }
    ds = xr.Dataset(attrs={'on_a_sphere': 'YES', 'sphere_radius': OLD_RADIUS})
    for suffix, dim in dims.items():
        for coord in 'xyz':
            ds[f'{coord}{suffix}'] = (
                (dim,),
                OLD_RADIUS * rng.uniform(-1.0, 1.0, sizes[dim]),
            )
    for name in ['dcEdge', 'dvEdge']:
        ds[name] = (('nEdges',), rng.uniform(1.0e5, 2.0e5, sizes['nEdges']))
    ds['areaCell'] = (
        ('nCells',),
        rng.uniform(1.0e10, 2.0e10, sizes['nCells']),
        {'units': 'm^2'},
    )
    ds['areaTriangle'] = (
        ('nVertices',),
        rng.uniform(1.0e10, 2.0e10, sizes['nVertices']),
    )
    ds['kiteAreasOnVertex'] = (
        ('nVertices', 'vertexDegree'),
        rng.uniform(1.0e9, 2.0e9, (sizes['nVertices'], 3)),
    )
    ds['latCell'] = (('nCells',), rng.uniform(-1.5, 1.5, sizes['nCells']))
    ds['layerThickness'] = (
        ('Time', 'nCells', 'nVertLevels'),
        rng.uniform(1.0, 100.0, (1, sizes['nCells'], 3)),
    )
    return ds
