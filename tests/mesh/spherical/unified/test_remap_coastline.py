import configparser
from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr

from polaris.component import Component
from polaris.mesh.spherical.coastline import CONVENTIONS
from polaris.mesh.spherical.unified.resolutions import FINEST_RESOLUTION
from polaris.tasks.mesh.spherical.unified.coastline import (
    get_unified_mesh_coastline_steps,
)
from polaris.tasks.mesh.spherical.unified.coastline import (
    remap as remap_module,
)
from polaris.tasks.mesh.spherical.unified.coastline import (
    steps as coastline_steps_module,
)
from polaris.tasks.mesh.spherical.unified.coastline.remap import (
    RemapCoastlineStep,
    _bilinear_zoom,
    _block_average,
    _coarsen_coordinate,
    _coastline_remap_dataset,
    _compute_scale,
)


def test_compute_scale_exact_multiple():
    assert _compute_scale(0.03125, 0.25) == 8
    assert _compute_scale(0.03125, 0.0625) == 2


def test_compute_scale_non_multiple_raises():
    with pytest.raises(ValueError):
        _compute_scale(0.03125, 0.1)


def test_block_average_2x_scale():
    arr = np.array(
        [
            [1.0, 0.0, 1.0, 1.0],
            [0.0, 1.0, 0.0, 1.0],
            [1.0, 1.0, 0.0, 0.0],
            [1.0, 1.0, 0.0, 0.0],
        ]
    )
    result = _block_average(arr, scale=2)
    expected = np.array(
        [
            [0.5, 0.75],
            [1.0, 0.0],
        ]
    )
    np.testing.assert_allclose(result, expected)


def test_block_average_all_ocean():
    arr = np.ones((4, 4))
    np.testing.assert_allclose(_block_average(arr, scale=2), np.ones((2, 2)))


def test_block_average_all_land():
    arr = np.zeros((4, 4))
    np.testing.assert_allclose(_block_average(arr, scale=2), np.zeros((2, 2)))


def test_bilinear_zoom_shape():
    arr = np.random.default_rng(0).random((16, 32))
    result = _bilinear_zoom(arr, scale=2)
    assert result.shape == (8, 16)


def test_bilinear_zoom_uniform_field():
    arr = np.full((8, 8), 3.5)
    result = _bilinear_zoom(arr, scale=2)
    np.testing.assert_allclose(result, np.full((4, 4), 3.5), atol=1e-12)


def test_coarsen_coordinate_mean():
    coord = np.array([1.0, 3.0, 5.0, 7.0])
    result = _coarsen_coordinate(coord, scale=2)
    np.testing.assert_allclose(result, np.array([2.0, 6.0]))


def test_remap_ocean_mask_threshold():
    # 4×4 fine mask: top-left 2×2 is all ocean, bottom-right is all land
    # → top-left coarse cell fraction 1.0 ≥ 0.5, bottom-right 0.0 < 0.5
    fine_mask = np.zeros((4, 4), dtype=np.float64)
    fine_mask[:2, :2] = 1.0
    fine_dist = np.where(fine_mask, 1000.0, -1000.0).astype(np.float64)

    ds_fine = _make_fine_dataset(fine_mask, fine_dist, n=4)
    ds_coarse = _coastline_remap_dataset(
        ds_fine=ds_fine,
        scale=2,
        mask_threshold=0.5,
        convention='bedrock_zero',
        fine_resolution=1.0,
        coarse_resolution=2.0,
        fine_step_subdir='fine/prepare',
    )

    ocean_mask = ds_coarse['ocean_mask'].values
    assert ocean_mask[0, 0] == 1
    assert ocean_mask[1, 1] == 0


def test_remap_signed_distance_sign_follows_mask():
    # All cells: fine mask = ocean (1), so coarse mask = ocean; distance > 0
    fine_mask = np.ones((4, 4), dtype=np.float64)
    fine_dist = 5000.0 * np.ones((4, 4), dtype=np.float64)
    ds_fine = _make_fine_dataset(fine_mask, fine_dist, n=4)

    ds_coarse = _coastline_remap_dataset(
        ds_fine=ds_fine,
        scale=2,
        mask_threshold=0.5,
        convention='bedrock_zero',
        fine_resolution=1.0,
        coarse_resolution=2.0,
        fine_step_subdir='fine/prepare',
    )
    signed_distance = ds_coarse['signed_distance'].values
    ocean_mask = ds_coarse['ocean_mask'].values
    assert np.all(signed_distance[ocean_mask == 1] > 0)

    # All land fine mask → all land coarse; distance < 0
    fine_mask_land = np.zeros((4, 4), dtype=np.float64)
    fine_dist_land = -5000.0 * np.ones((4, 4), dtype=np.float64)
    ds_fine_land = _make_fine_dataset(fine_mask_land, fine_dist_land, n=4)
    ds_coarse_land = _coastline_remap_dataset(
        ds_fine=ds_fine_land,
        scale=2,
        mask_threshold=0.5,
        convention='bedrock_zero',
        fine_resolution=1.0,
        coarse_resolution=2.0,
        fine_step_subdir='fine/prepare',
    )
    signed_distance_land = ds_coarse_land['signed_distance'].values
    assert np.all(signed_distance_land < 0)


def test_remap_mixed_mask_sign_consistency():
    # Top row ocean, bottom row land at fine resolution
    # (scale=2 → 1 coarse row each)
    fine_mask = np.zeros((4, 4), dtype=np.float64)
    fine_mask[:2, :] = 1.0
    fine_dist = np.where(fine_mask, 2000.0, -2000.0).astype(np.float64)
    ds_fine = _make_fine_dataset(fine_mask, fine_dist, n=4)

    ds_coarse = _coastline_remap_dataset(
        ds_fine=ds_fine,
        scale=2,
        mask_threshold=0.5,
        convention='grounding_line',
        fine_resolution=1.0,
        coarse_resolution=2.0,
        fine_step_subdir='fine/prepare',
    )
    ocean_mask = ds_coarse['ocean_mask'].values
    signed_distance = ds_coarse['signed_distance'].values

    ocean_rows = np.where(ocean_mask[..., 0] == 1)[0]
    land_rows = np.where(ocean_mask[..., 0] == 0)[0]
    assert np.all(signed_distance[ocean_rows, :] > 0)
    assert np.all(signed_distance[land_rows, :] < 0)


def test_remap_dataset_attributes():
    fine_mask = np.ones((4, 4), dtype=np.float64)
    fine_dist = np.ones((4, 4), dtype=np.float64) * 3000.0
    ds_fine = _make_fine_dataset(fine_mask, fine_dist, n=4)

    ds_coarse = _coastline_remap_dataset(
        ds_fine=ds_fine,
        scale=2,
        mask_threshold=0.5,
        convention='calving_front',
        fine_resolution=0.03125,
        coarse_resolution=0.25,
        fine_step_subdir='spherical/unified/coastline/lat_lon/0p03125/prepare',
    )
    assert ds_coarse.attrs['coastline_convention'] == 'calving_front'
    assert ds_coarse.attrs['target_grid_resolution_degrees'] == 0.25
    assert ds_coarse.attrs['source_resolution_degrees'] == 0.03125
    assert ds_coarse.attrs['coastline_source'] == 'remapped_from_fine_grid'
    assert '0.03125' in ds_coarse.attrs['coastline_edge_definition']
    assert ds_coarse['signed_distance'].attrs['units'] == 'm'


def test_coastline_remap_step_writes_all_conventions(tmp_path, monkeypatch):
    component = Component('mesh')
    fine_mask = np.ones((4, 4), dtype=np.float64)
    fine_dist = 4000.0 * np.ones((4, 4), dtype=np.float64)

    fine_output_filenames = {
        convention: f'coastline_{convention}.nc' for convention in CONVENTIONS
    }
    fine_step = SimpleNamespace(
        output_filenames=fine_output_filenames,
        path=str(tmp_path),
        subdir='fine/prepare',
    )

    # Write synthetic fine files with the prefixed names that run() expects
    for convention in CONVENTIONS:
        ds = _make_fine_dataset(fine_mask, fine_dist, n=4)
        ds.to_netcdf(tmp_path / f'fine_{fine_output_filenames[convention]}')

    step = RemapCoastlineStep(
        component=component,
        fine_coastline_step=fine_step,
        coarse_resolution=2 * FINEST_RESOLUTION,
        subdir='coarse/prepare',
    )
    step.config = _make_remap_config()

    written = {}

    def fake_write(ds, filename):
        written[filename] = ds

    monkeypatch.setattr(
        remap_module, '_write_netcdf_with_fill_values', fake_write
    )
    monkeypatch.chdir(tmp_path)
    step.run()

    assert set(written.keys()) == set(fine_output_filenames.values())
    for ds in written.values():
        assert 'ocean_mask' in ds
        assert 'signed_distance' in ds
        assert ds['ocean_mask'].shape == (2, 2)


def test_get_unified_mesh_coastline_steps_creates_remap_step_for_coarse(
    monkeypatch,
):
    component = Component('mesh')
    monkeypatch.setattr(
        coastline_steps_module, '_get_mesh_component', lambda: component
    )

    steps, _ = get_unified_mesh_coastline_steps(
        resolution=0.25,
        include_viz=False,
    )
    assert 'coastline_final' in steps
    assert isinstance(steps['coastline_final'], RemapCoastlineStep)


def _make_fine_dataset(ocean_mask, signed_distance, n):
    lon = np.linspace(0.0, 360.0 - 360.0 / n, n)
    lat = np.linspace(-90.0 + 180.0 / n, 90.0 - 180.0 / n, n)
    return xr.Dataset(
        data_vars=dict(
            ocean_mask=(('lat', 'lon'), ocean_mask.astype(np.int8)),
            signed_distance=(
                ('lat', 'lon'),
                signed_distance.astype(np.float32),
            ),
        ),
        coords=dict(
            lat=xr.DataArray(lat, dims=('lat',)),
            lon=xr.DataArray(lon, dims=('lon',)),
        ),
    )


def _make_remap_config():
    config = configparser.ConfigParser()
    config.add_section('coastline')
    config.set('coastline', 'mask_threshold', '0.5')
    config.set('coastline', 'resolution_latlon', '2.0')
    return config
