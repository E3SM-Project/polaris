import pytest

from polaris.config import PolarisConfigParser
from polaris.e3sm.init.glc_ocean_maps import GlcOceanMapStep


class _FakeComponent:
    name = 'fake'


def _make_step(**kwargs):
    kwargs.setdefault('glc_mesh_name', 'li1km')
    kwargs.setdefault('ocn_mesh_name', 'o4km')
    return GlcOceanMapStep(
        component=_FakeComponent(), name='map', subdir='map', **kwargs
    )


def _run_runtime_setup(step, tmp_path, monkeypatch):
    config = PolarisConfigParser()
    config.set('mapping', 'map_tool', 'moab')
    step.config = config
    step.work_dir = str(tmp_path)

    def prepare_map(logger=None):
        step.remapper.map_filename = 'map.nc'
        return ['mbtempest']

    monkeypatch.setattr(step.remapper, 'prepare_map', prepare_map)
    monkeypatch.chdir(tmp_path)
    step.runtime_setup()


def test_map_is_conservative():
    step = _make_step(to_ocean=True)
    assert step.remapper.method == 'conserve'
    assert 'map.nc' in step.outputs


def test_map_to_the_ocean_reads_both_scrip_files(tmp_path, monkeypatch):
    step = _make_step(to_ocean=True)
    _run_runtime_setup(step, tmp_path, monkeypatch)
    assert step.remapper.src_descriptor.filename == str(
        tmp_path / 'glc_scrip.nc'
    )
    assert step.remapper.dst_descriptor.filename == str(
        tmp_path / 'ocn_scrip.nc'
    )
    assert step.remapper.expand_dist is None


def test_map_to_the_land_ice_swaps_the_grids(tmp_path, monkeypatch):
    step = _make_step(to_ocean=False)
    _run_runtime_setup(step, tmp_path, monkeypatch)
    assert step.remapper.src_descriptor.filename == str(
        tmp_path / 'ocn_scrip.nc'
    )
    assert step.remapper.dst_descriptor.filename == str(
        tmp_path / 'glc_scrip.nc'
    )


def test_smoothed_map_inflates_the_ocean_mesh(tmp_path, monkeypatch):
    step = _make_step(to_ocean=True, smoothed=True, expand_distance=4000.0)
    _run_runtime_setup(step, tmp_path, monkeypatch)
    assert step.remapper.expand_dist == 4000.0
    assert step.remapper.src_descriptor.filename == str(
        tmp_path / 'glc_scrip.nc'
    )
    assert step.remapper.dst_grid_info['filename'] == str(
        tmp_path / 'ocn_mesh.nc'
    )


def test_expand_distance_may_be_set_after_creation(tmp_path, monkeypatch):
    step = _make_step(to_ocean=True, smoothed=True)
    step.expand_distance = 2000.0
    _run_runtime_setup(step, tmp_path, monkeypatch)
    assert step.remapper.expand_dist == 2000.0


@pytest.mark.parametrize('expand_distance', [None, 0.0, -1.0])
def test_smoothed_map_needs_a_positive_distance(
    tmp_path, monkeypatch, expand_distance
):
    step = _make_step(
        to_ocean=True, smoothed=True, expand_distance=expand_distance
    )
    with pytest.raises(ValueError, match='positive expand_distance'):
        _run_runtime_setup(step, tmp_path, monkeypatch)


def test_only_a_map_to_the_ocean_can_be_smoothed():
    with pytest.raises(ValueError, match='Only a map from the land ice'):
        _make_step(to_ocean=False, smoothed=True, expand_distance=4000.0)


def test_mesh_names_are_required(tmp_path, monkeypatch):
    step = _make_step(to_ocean=True, ocn_mesh_name=None)
    with pytest.raises(ValueError, match='mesh_name'):
        _run_runtime_setup(step, tmp_path, monkeypatch)
