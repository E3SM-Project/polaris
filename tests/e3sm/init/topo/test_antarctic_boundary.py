import numpy as np
import pytest
import xarray as xr

from polaris.config import PolarisConfigParser
from polaris.tasks.e3sm.init.topo.cull.mask import CullMaskStep
from polaris.tasks.e3sm.init.topo.cull.steps import _get_cull_topo_config
from polaris.tasks.e3sm.init.topo.remap.mask import MaskTopoStep
from polaris.tasks.e3sm.init.topo.remap.steps import _get_remap_topo_config


@pytest.mark.parametrize(
    ('convention', 'expected_ocean'),
    [
        ('calving_front', [0.0, 0.0, 1.0, 0.0]),
        ('grounding_line', [0.0, 1.0, 1.0, 0.0]),
        ('bedrock_zero', [1.0, 1.0, 1.0, 0.0]),
    ],
)
def test_remap_mask_antarctic_boundary_convention(convention, expected_ocean):
    step = _mask_topo_step(convention=convention)
    ocean_mask, land_mask = step.define_masks(_topo_dataset())

    np.testing.assert_allclose(ocean_mask.values, expected_ocean)
    np.testing.assert_allclose(land_mask.values, [1.0, 1.0, 0.0, 1.0])


def test_remap_mask_requires_antarctic_boundary_convention():
    step = _mask_topo_step(convention=None)

    with pytest.raises(ValueError, match='Missing spherical_mesh'):
        step.define_masks(_topo_dataset())


def test_remap_mask_rejects_invalid_antarctic_boundary_convention():
    step = _mask_topo_step(convention='ice_shelf_edge')

    with pytest.raises(ValueError, match='Unexpected'):
        step.define_masks(_topo_dataset())


def test_spherical_mesh_config_default_convention():
    config = PolarisConfigParser()
    config.add_from_package('polaris.mesh.spherical', 'spherical.cfg')

    assert (
        config.get('spherical_mesh', 'antarctic_boundary_convention')
        == 'calving_front'
    )


def test_topo_configs_inherit_base_mesh_convention():
    base_mesh_step = _base_mesh_step(convention='bedrock_zero')

    remap_config = _get_remap_topo_config(
        filepath='test/QU240/topo/remap/remap_topo.cfg',
        base_mesh_step=base_mesh_step,
        low_res=False,
    )
    cull_config = _get_cull_topo_config(
        filepath='test/QU240/topo/cull/cull_topo.cfg',
        base_mesh_step=base_mesh_step,
    )

    for config in [remap_config, cull_config]:
        assert (
            config.get('spherical_mesh', 'antarctic_boundary_convention')
            == 'bedrock_zero'
        )


def test_antarctic_land_ice_ownership_includes_southern_non_ocean_cells():
    ds_topo = _cull_topo_dataset(
        ocean_frac=[1.0, 0.0, 0.0],
        land_frac=[0.0, 1.0, 1.0],
        ice_frac=[0.2, 0.0, 0.0],
        grounded_mask=[0.0, 0.0, 0.0],
        base_elevation=[-100.0, 100.0, 100.0],
    )
    ocean_cull_mask = xr.DataArray([False, True, True], dims=('nCells',))
    lat_cell = xr.DataArray([-80.0, -75.0, -40.0], dims=('nCells',))

    land_ice = CullMaskStep._antarctic_land_ice_ownership(
        ds_topo=ds_topo,
        ocean_cull_mask=ocean_cull_mask,
        lat_cell=lat_cell,
        land_ice_max_latitude=-60.0,
        land_ice_min_fraction=0.01,
    )

    np.testing.assert_array_equal(land_ice.values, [True, True, False])


def _mask_topo_step(convention):
    config = PolarisConfigParser()
    if convention is not None:
        config.add_from_package('polaris.mesh.spherical', 'spherical.cfg')
        config.set(
            'spherical_mesh', 'antarctic_boundary_convention', convention
        )

    step = MaskTopoStep.__new__(MaskTopoStep)
    step.config = config
    return step


class _BaseMeshStep:
    def __init__(self, convention):
        self.mesh_name = 'QU240'
        self.config = PolarisConfigParser()
        self.config.add_from_package('polaris.mesh.spherical', 'spherical.cfg')
        self.config.set('spherical_mesh', 'prefix', 'QU')
        self.config.set('spherical_mesh', 'min_cell_width', '240')
        self.config.set('spherical_mesh', 'max_cell_width', '240')
        self.config.set(
            'spherical_mesh', 'antarctic_boundary_convention', convention
        )


def _base_mesh_step(convention):
    return _BaseMeshStep(convention)


def _topo_dataset():
    return xr.Dataset(
        data_vars=dict(
            base_elevation=(
                'nCells',
                np.array([-100.0, -100.0, -100.0, 1.0]),
            ),
            ice_mask=('nCells', np.array([1.0, 1.0, 0.0, 0.0])),
            grounded_mask=('nCells', np.array([1.0, 0.0, 0.0, 0.0])),
        )
    )


def _cull_topo_dataset(
    ocean_frac,
    land_frac,
    ice_frac,
    grounded_mask,
    base_elevation,
):
    return xr.Dataset(
        data_vars=dict(
            ocean_frac=('nCells', np.asarray(ocean_frac, dtype=float)),
            land_frac=('nCells', np.asarray(land_frac, dtype=float)),
            ice_frac=('nCells', np.asarray(ice_frac, dtype=float)),
            grounded_mask=(
                'nCells',
                np.asarray(grounded_mask, dtype=float),
            ),
            base_elevation=(
                'nCells',
                np.asarray(base_elevation, dtype=float),
            ),
        )
    )
