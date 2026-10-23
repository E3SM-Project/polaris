import cfunits
import pytest
import xarray as xr
from mpas_tools.planar_hex import make_planar_hex_mesh

from polaris.cf import (
    CF_VERSION,
    add_cf_conventions,
    add_lat_lon_attrs,
    add_var_attrs,
    drop_dangling_references,
    drop_inherited_attrs,
    read_var_attrs,
)
from polaris.mesh.attrs import add_mesh_var_attrs

# the tables of variable attributes Polaris fills in before writing a file
TABLES = [
    ('polaris.ocean.model', 'attrs.yaml'),
]


def test_conventions_added_when_missing():
    ds = add_cf_conventions(xr.Dataset())
    assert ds.attrs['Conventions'] == f'CF-{CF_VERSION}'


def test_conventions_keeps_mpas():
    """The mesh converter's MPAS entry stays, after the CF one"""
    ds_in = xr.Dataset(attrs={'Conventions': 'MPAS'})
    ds = add_cf_conventions(ds_in)
    assert ds.attrs['Conventions'] == f'CF-{CF_VERSION} MPAS'
    # the input is not modified
    assert ds_in.attrs['Conventions'] == 'MPAS'


@pytest.mark.parametrize('existing', ['CF-1.6', 'CF-1.6, UGRID-1.0'])
def test_conventions_with_cf_entry_untouched(existing):
    ds = add_cf_conventions(xr.Dataset(attrs={'Conventions': existing}))
    assert ds.attrs['Conventions'] == existing


def test_var_attrs_fill_only_what_is_missing():
    ds_in = xr.Dataset(
        data_vars=dict(
            xCell=('nCells', [0.0, 1.0], {'long_name': 'from the tool'}),
            yCell=('nCells', [0.0, 1.0]),
        )
    )
    table = {
        'xCell': {'long_name': 'x coordinate', 'units': 'm'},
        'yCell': {'long_name': 'y coordinate', 'units': 'm'},
        'zCell': {'long_name': 'z coordinate', 'units': 'm'},
    }
    ds = add_var_attrs(ds_in, table)
    assert ds.xCell.attrs == {'long_name': 'from the tool', 'units': 'm'}
    assert ds.yCell.attrs == {'long_name': 'y coordinate', 'units': 'm'}
    assert 'zCell' not in ds
    # the input is not modified
    assert ds_in.xCell.attrs == {'long_name': 'from the tool'}
    assert ds_in.yCell.attrs == {}


def test_inherited_attrs_are_dropped():
    """A variable derived from another with xarray carries that variable's
    attributes; a variable labeled on its own keeps them"""
    x_cell = xr.DataArray(
        [0.0, 1.0], dims='nCells', attrs={'long_name': 'x', 'units': 'm'}
    )
    ds_in = xr.Dataset(
        data_vars=dict(
            xCell=x_cell,
            bottomDepth=100.0 * xr.ones_like(x_cell),
            ssh=('nCells', [0.0, 0.0], {'long_name': 'ssh'}),
        )
    )
    ds = drop_inherited_attrs(ds_in, ['bottomDepth', 'ssh', 'missing'])
    assert ds.bottomDepth.attrs == {}
    assert ds.ssh.attrs == {'long_name': 'ssh'}
    assert ds.xCell.attrs == x_cell.attrs
    # the input is not modified
    assert ds_in.bottomDepth.attrs == x_cell.attrs


def test_lat_lon_attrs_fill_only_what_is_missing():
    ds_in = xr.Dataset(
        coords=dict(
            lat=('lat', [-45.0, 45.0]),
            lon=('lon', [90.0, 270.0], {'long_name': 'from the source'}),
        )
    )
    ds = add_lat_lon_attrs(ds_in)
    assert ds.lat.attrs == {
        'long_name': 'latitude',
        'standard_name': 'latitude',
        'units': 'degrees_north',
    }
    assert ds.lon.attrs['long_name'] == 'from the source'
    assert ds.lon.attrs['units'] == 'degrees_east'
    # the input is not modified
    assert ds_in.lat.attrs == {}


def test_dangling_references_are_dropped():
    """Attributes naming variables a remapped file no longer has go, from
    the attributes and from the encoding; ones naming variables it has
    stay"""
    ds_in = xr.Dataset(
        data_vars=dict(
            ct_an=(
                'nCells',
                [1.0, 2.0],
                {
                    'cell_measures': 'area: area',
                    'grid_mapping': 'crs',
                    'ancillary_variables': 'lat',
                },
            ),
            lat=('nCells', [0.0, 1.0], {'bounds': 'lat_vertices'}),
            depth=('nCells', [5.0, 10.0], {'bounds': 'lat'}),
        )
    )
    ds_in.ct_an.encoding['coordinates'] = 'lat lon'
    ds = drop_dangling_references(ds_in)
    assert ds.ct_an.attrs == {'ancillary_variables': 'lat'}
    assert 'coordinates' not in ds.ct_an.encoding
    assert ds.lat.attrs == {}
    assert ds.depth.attrs == {'bounds': 'lat'}
    # the input is not modified
    assert ds_in.lat.attrs == {'bounds': 'lat_vertices'}
    assert ds_in.ct_an.encoding['coordinates'] == 'lat lon'


@pytest.mark.parametrize('package,filename', TABLES)
def test_table_entries_are_valid(package, filename):
    """Every entry has a long_name and any units are ones udunits parses, so
    the CF checker will accept them"""
    var_attrs = read_var_attrs(package, filename)
    assert len(var_attrs) > 0
    for name, attrs in var_attrs.items():
        assert 'long_name' in attrs, name
        if 'units' in attrs:
            assert cfunits.Units(attrs['units']).isvalid, (
                f'{name}: {attrs["units"]}'
            )


def test_planar_hex_mesh_gets_mesh_attrs():
    """every variable of a planar mesh has a long_name and every non-integer
    one has units"""
    ds = add_mesh_var_attrs(
        make_planar_hex_mesh(
            nx=4, ny=4, dc=1e3, nonperiodic_x=False, nonperiodic_y=True
        )
    )
    for name, da in ds.data_vars.items():
        assert 'long_name' in da.attrs, name
        if da.dtype.kind == 'f':
            assert 'units' in da.attrs, name


@pytest.mark.parametrize(
    'on_a_sphere, standard_name', [('YES', 'latitude'), ('NO', None)]
)
def test_mesh_latitude_standard_name(on_a_sphere, standard_name):
    """only a spherical mesh's latitude gets a standard_name"""
    ds = xr.Dataset(
        {'latCell': ('nCells', [0.0])}, attrs={'on_a_sphere': on_a_sphere}
    )
    ds = add_mesh_var_attrs(ds)
    assert ds.latCell.attrs.get('standard_name') == standard_name


def test_mesh_standard_name_kept_without_on_a_sphere():
    """a dataset that has lost on_a_sphere keeps the standard names its mesh
    variables came with, and gains none"""
    ds = xr.Dataset(
        {
            'latCell': ('nCells', [0.0], {'standard_name': 'latitude'}),
            'lonCell': ('nCells', [0.0]),
        }
    )
    ds = add_mesh_var_attrs(ds)
    assert ds.latCell.attrs['standard_name'] == 'latitude'
    assert 'standard_name' not in ds.lonCell.attrs
