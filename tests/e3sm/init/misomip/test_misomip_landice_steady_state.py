import netCDF4
import numpy as np
import pytest

from polaris.tasks.e3sm.init.misomip.landice_steady_state import (
    LANDICE_MESH_LENGTH,
    copy_by_position,
    remove_masked_ice,
)
from polaris.tasks.e3sm.init.misomip.steps import (
    get_misomip_experiment_steps,
)


def _write_mesh(filename, x_cell, fields):
    """
    Write a small MALI-like file whose cells lie along y = 0, with an edge
    and a vertex beside each cell
    """
    with netCDF4.Dataset(filename, 'w') as ds:
        ds.createDimension('Time', None)
        ds.createDimension('StrLen', 4)
        ds.createDimension('nVertLevels', 2)
        for dim in ['nCells', 'nEdges', 'nVertices']:
            ds.createDimension(dim, len(x_cell))
        offsets = {'Cell': 0.0, 'Edge': 0.5, 'Vertex': 0.25}
        dims = {'Cell': 'nCells', 'Edge': 'nEdges', 'Vertex': 'nVertices'}
        for loc, offset in offsets.items():
            x = np.asarray(x_cell, dtype=float) + offset
            ds.createVariable(f'x{loc}', 'f8', (dims[loc],))[:] = x
            ds.createVariable(f'y{loc}', 'f8', (dims[loc],))[:] = 0.0
        ds.createVariable('areaCell', 'f8', ('nCells',))[:] = 10.0 * (
            1.0 + np.arange(len(x_cell))
        )
        for name, (dims, dtype, values) in fields.items():
            ds.createVariable(name, dtype, dims)[:] = values


def test_copy_by_position(tmp_path):
    src = str(tmp_path / 'src.nc')
    dst = str(tmp_path / 'dst.nc')
    out = str(tmp_path / 'out.nc')
    # the source's cells, in another order, then a new cell
    x_src = [0.0, 1000.0, 2000.0]
    x_dst = [2000.0, 0.0, 1000.0, 3000.0]
    _write_mesh(
        src,
        x_src,
        {
            'thickness': (('Time', 'nCells'), 'f8', [[100.0, 50.0, 5.0]]),
            'calvingMask': (('Time', 'nCells'), 'i4', [[0, 0, 1]]),
            'temperature': (
                ('Time', 'nCells', 'nVertLevels'),
                'f8',
                [[[250.0, 251.0], [252.0, 253.0], [254.0, 255.0]]],
            ),
            'normalVelocity': (('Time', 'nEdges'), 'f8', [[1.0, 2.0, 3.0]]),
            'xtime': (
                ('Time', 'StrLen'),
                'S1',
                np.array([list('0001')], dtype='S1'),
            ),
        },
    )
    _write_mesh(
        dst,
        x_dst,
        {
            'thickness': (('Time', 'nCells'), 'f8', [[9.0, 9.0, 9.0, 0.0]]),
            'calvingMask': (('Time', 'nCells'), 'i4', [[0, 0, 0, 1]]),
        },
    )

    copy_by_position(src, dst, out, mesh_variables={'areaCell'})
    removed = remove_masked_ice(out)

    with netCDF4.Dataset(out) as ds:
        ds.set_auto_mask(False)
        # the source's values at their positions, and the template's in
        # the new cell
        np.testing.assert_array_equal(
            ds.variables['calvingMask'][0, :], [1, 0, 0, 1]
        )
        # the ice where the calving mask is 1 is removed
        np.testing.assert_array_equal(
            ds.variables['thickness'][0, :], [0.0, 100.0, 50.0, 0.0]
        )
        # a field the template lacks is zero in the new cell
        np.testing.assert_array_equal(
            ds.variables['temperature'][0, :, :],
            [[254.0, 255.0], [250.0, 251.0], [252.0, 253.0], [0.0, 0.0]],
        )
        np.testing.assert_array_equal(
            ds.variables['normalVelocity'][0, :], [3.0, 1.0, 2.0, 0.0]
        )
        assert b''.join(ds.variables['xtime'][0, :]) == b'0001'
        # the mesh keeps the larger mesh's values
        np.testing.assert_array_equal(
            ds.variables['areaCell'][:], [10.0, 20.0, 30.0, 40.0]
        )
    assert removed == 1


def test_copy_by_position_needs_every_position(tmp_path):
    src = str(tmp_path / 'src.nc')
    dst = str(tmp_path / 'dst.nc')
    _write_mesh(src, [0.0, 1500.0], {})
    _write_mesh(dst, [0.0, 1000.0, 2000.0], {})
    with pytest.raises(ValueError, match='No Cell of the destination mesh'):
        copy_by_position(src, dst, str(tmp_path / 'out.nc'), set())


def test_landice_steady_state_steps():
    steps, _ = get_misomip_experiment_steps('misomip-o4km-li1km', 'ocean0')
    mesh = steps['mismip_plus/mesh']
    assert mesh.length == LANDICE_MESH_LENGTH
    assert mesh.path == 'mesh/planar/mismip_plus/1km/660km/mesh'
    steady_state = steps['landice_steady_state']
    targets = [entry['work_dir_target'] for entry in steady_state.input_data]
    # the steady state comes from the domain's 640 km mesh
    assert 'landice/mismip_plus/1km/spin_up/spin_up/steady_state.nc' in targets
    # MALI's initial condition starts from the copy on the longer mesh
    targets = [
        entry['work_dir_target'] for entry in steps['landice_init'].input_data
    ]
    assert f'{steady_state.path}/steady_state.nc' in targets
