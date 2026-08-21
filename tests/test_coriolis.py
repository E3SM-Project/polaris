"""
Unit tests for the framework's Coriolis helpers.

All tests are self-contained: no file I/O and no full Polaris step
framework.  A small mesh dataset and a ``PolarisConfigParser`` holding
only the ``[coriolis]`` section are constructed in each test.
"""

import numpy as np
import pytest
import xarray as xr

from polaris.config import PolarisConfigParser
from polaris.constants import get_constant
from polaris.coriolis import (
    add_beta_plane_coriolis,
    add_constant_coriolis,
    add_coriolis_to_dataset,
    add_rotated_sphere_coriolis,
    add_spherical_coriolis,
    add_zero_coriolis,
)

OMEGA = get_constant('angular_velocity')

FIELDS = ['fCell', 'fEdge', 'fVertex']

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# a few latitudes spanning both hemispheres, in radians
LATS = np.deg2rad(np.array([-90.0, -30.0, 0.0, 45.0, 90.0]))

# longitudes chosen so that cos(lon) is not the same at every point
LONS = np.deg2rad(np.array([0.0, 90.0, 180.0, 270.0, 45.0]))


def _make_mesh():
    """
    A minimal horizontal mesh with the same number of cells, edges and
    vertices, so that a single set of coordinates can be reused at all
    three locations
    """
    x = np.linspace(0.0, 4.0e5, LATS.size)
    y = np.linspace(-2.0e5, 2.0e5, LATS.size)
    ds_mesh = xr.Dataset()
    for location, dim in [
        ('Cell', 'nCells'),
        ('Edge', 'nEdges'),
        ('Vertex', 'nVertices'),
    ]:
        ds_mesh[f'x{location}'] = (dim, x)
        ds_mesh[f'y{location}'] = (dim, y)
        ds_mesh[f'lon{location}'] = (dim, LONS)
        ds_mesh[f'lat{location}'] = (dim, LATS)
    return ds_mesh


def _make_config(**options):
    """
    A config parser with a ``[coriolis]`` section containing only the
    given options, so that anything a helper reads but the test did not
    set is missing rather than defaulted
    """
    config = PolarisConfigParser()
    config.add_section('coriolis')
    for option, value in options.items():
        config.set('coriolis', option, value)
    return config


# ---------------------------------------------------------------------------
# The individual helpers
# ---------------------------------------------------------------------------


def test_zero_coriolis():
    ds_mesh = add_zero_coriolis(_make_mesh())
    for field in FIELDS:
        assert np.all(ds_mesh[field].values == 0.0)


@pytest.mark.parametrize('f', [1.0e-4, -1.2e-4, 0.0])
def test_constant_coriolis(f):
    ds_mesh = add_constant_coriolis(_make_mesh(), f)
    for field in FIELDS:
        assert ds_mesh[field].values == pytest.approx(f)


def test_beta_plane_coriolis():
    f0 = 1.0e-4
    beta = 1.0e-11
    ds_mesh = add_beta_plane_coriolis(_make_mesh(), f0, beta)
    coords = ['yCell', 'yEdge', 'yVertex']
    for field, coord in zip(FIELDS, coords, strict=True):
        expected = f0 + beta * ds_mesh[coord].values
        assert ds_mesh[field].values == pytest.approx(expected)


def test_spherical_coriolis():
    ds_mesh = add_spherical_coriolis(_make_mesh())
    expected = 2.0 * OMEGA * np.sin(LATS)
    for field in FIELDS:
        assert ds_mesh[field].values == pytest.approx(expected)


def test_spherical_coriolis_omega():
    """A supplied rotation rate is used in place of the Earth's"""
    omega = 1.0e-4
    ds_mesh = add_spherical_coriolis(_make_mesh(), omega=omega)
    expected = 2.0 * omega * np.sin(LATS)
    for field in FIELDS:
        assert ds_mesh[field].values == pytest.approx(expected)


def test_rotated_sphere_coriolis_no_rotation():
    """``alpha=0`` is the same as rotation about the Earth's axis"""
    ds_rotated = add_rotated_sphere_coriolis(_make_mesh(), alpha=0.0)
    ds_spherical = add_spherical_coriolis(_make_mesh())
    for field in FIELDS:
        assert ds_rotated[field].values == pytest.approx(
            ds_spherical[field].values
        )


def test_rotated_sphere_coriolis_pole_on_equator():
    """
    With ``alpha=pi/2`` the rotation axis lies in the equatorial plane, so
    the extrema are on the equator rather than at the geographic poles
    """
    ds_mesh = add_rotated_sphere_coriolis(_make_mesh(), alpha=0.5 * np.pi)
    expected = -2.0 * OMEGA * np.cos(LONS) * np.cos(LATS)
    for field in FIELDS:
        assert ds_mesh[field].values == pytest.approx(expected)

    # the geographic poles, where the unrotated f is largest, now have no
    # rotation at all
    poles = np.abs(np.abs(LATS) - 0.5 * np.pi) < 1.0e-12
    assert np.any(poles)
    assert ds_mesh.fCell.values[poles] == pytest.approx(0.0)


def test_coriolis_attrs():
    ds_mesh = add_zero_coriolis(_make_mesh())
    for field, location in zip(
        FIELDS, ['cell centers', 'edges', 'vertices'], strict=True
    ):
        attrs = ds_mesh[field].attrs
        assert attrs['long_name'] == f'Coriolis parameter at {location}'
        assert attrs['standard_name'] == 'coriolis_parameter'
        assert attrs['units'] == 'radians s^-1'


# ---------------------------------------------------------------------------
# Dispatch from config options
# ---------------------------------------------------------------------------


def test_dispatch_zero():
    config = _make_config(type='zero')
    ds_mesh = add_coriolis_to_dataset(config, _make_mesh())
    assert np.all(ds_mesh.fCell.values == 0.0)


def test_dispatch_constant():
    config = _make_config(type='constant', constant_f='-1.2e-4')
    ds_mesh = add_coriolis_to_dataset(config, _make_mesh())
    assert ds_mesh.fCell.values == pytest.approx(-1.2e-4)


def test_dispatch_beta_plane():
    config = _make_config(
        type='beta_plane', beta_plane_f0='1.0e-4', beta_plane_beta='1.0e-11'
    )
    ds_mesh = add_coriolis_to_dataset(config, _make_mesh())
    expected = 1.0e-4 + 1.0e-11 * ds_mesh.yCell.values
    assert ds_mesh.fCell.values == pytest.approx(expected)


def test_dispatch_spherical():
    config = _make_config(type='spherical')
    ds_mesh = add_coriolis_to_dataset(config, _make_mesh())
    assert ds_mesh.fCell.values == pytest.approx(2.0 * OMEGA * np.sin(LATS))


def test_dispatch_rotated_sphere():
    alpha = 0.25 * np.pi
    config = _make_config(
        type='rotated_sphere', rotated_sphere_alpha=str(alpha)
    )
    ds_mesh = add_coriolis_to_dataset(config, _make_mesh())
    expected = add_rotated_sphere_coriolis(_make_mesh(), alpha).fCell.values
    assert ds_mesh.fCell.values == pytest.approx(expected)


def test_dispatch_whitespace_is_stripped():
    config = _make_config(type=' zero ')
    ds_mesh = add_coriolis_to_dataset(config, _make_mesh())
    assert np.all(ds_mesh.fCell.values == 0.0)


def test_dispatch_unknown_type():
    config = _make_config(type='f_plane')
    with pytest.raises(ValueError, match='Unsupported Coriolis type: f_plane'):
        add_coriolis_to_dataset(config, _make_mesh())


# ---------------------------------------------------------------------------
# Options that a task has to state for itself
# ---------------------------------------------------------------------------


def test_absent_type_raises():
    config = _make_config()
    with pytest.raises(ValueError, match='"type" config option'):
        add_coriolis_to_dataset(config, _make_mesh())


@pytest.mark.parametrize('type_value', ['', '   '])
def test_blank_type_raises(type_value):
    config = _make_config(type=type_value)
    with pytest.raises(ValueError, match='"type" config option'):
        add_coriolis_to_dataset(config, _make_mesh())


@pytest.mark.parametrize('blank', [True, False], ids=['blank', 'absent'])
@pytest.mark.parametrize(
    'coriolis_type, options, missing',
    [
        ('constant', {}, 'constant_f'),
        ('beta_plane', {'beta_plane_beta': '1.0e-11'}, 'beta_plane_f0'),
        ('beta_plane', {'beta_plane_f0': '1.0e-4'}, 'beta_plane_beta'),
        ('rotated_sphere', {}, 'rotated_sphere_alpha'),
    ],
)
def test_missing_parameter_raises(coriolis_type, options, missing, blank):
    """The message names the option that the task failed to set"""
    if blank:
        options = dict(options, **{missing: ''})
    config = _make_config(type=coriolis_type, **options)
    with pytest.raises(ValueError, match=f'"{missing}" config option'):
        add_coriolis_to_dataset(config, _make_mesh())


def test_unused_parameters_may_be_blank():
    """
    Only the parameter belonging to the selected type is read, so leaving
    the others blank -- as ``default.cfg`` does -- is never a problem
    """
    config = _make_config(
        type='constant',
        constant_f='1.0e-4',
        beta_plane_f0='',
        beta_plane_beta='',
        rotated_sphere_alpha='',
    )
    ds_mesh = add_coriolis_to_dataset(config, _make_mesh())
    assert ds_mesh.fCell.values == pytest.approx(1.0e-4)
