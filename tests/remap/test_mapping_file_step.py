from polaris.config import PolarisConfigParser
from polaris.remap import MappingFileStep


class _FakeComponent:
    name = 'fake'


def _make_step(**kwargs):
    return MappingFileStep(
        component=_FakeComponent(),
        name='map',
        subdir='map',
        **kwargs,
    )


def test_remapper_does_not_use_tmp():
    """
    /tmp is node-local on many HPC machines, so the SCRIP and .h5m files
    must go in the step's work directory instead.
    """
    step = _make_step()
    assert step.remapper.use_tmp is False


def test_remapper_method_is_passed_through():
    step = _make_step(method='conserve')
    assert step.remapper.method == 'conserve'


def test_remapper_defaults_to_bilinear():
    step = _make_step()
    assert step.remapper.method == 'bilinear'


def test_remapper_ntasks_is_passed_through():
    step = _make_step(ntasks=128, min_tasks=16)
    assert step.remapper.ntasks == 128


def test_step_launches_through_its_command():
    """
    The step says it launches from the start, long before its grids are
    known, so the framework never takes it for a step that only runs python
    """
    step = _make_step()
    assert step.args == []


def test_runtime_setup_sets_the_mapping_command(tmp_path, monkeypatch):
    step = _make_step(ntasks=4, min_tasks=1)
    config = PolarisConfigParser()
    config.set('mapping', 'map_tool', 'moab')
    step.config = config
    step.work_dir = str(tmp_path)
    step.remapper.src_from_mpas(filename='mesh.nc', mesh_name='QU240')
    step.remapper.dst_global_lon_lat(dlon=10.0, dlat=10.0)

    def prepare_map(logger=None):
        # pyremap names the map when it writes the files the tool reads
        step.remapper.map_filename = 'map.nc'
        return ['mbtempest', '--file', 'map.nc']

    monkeypatch.setattr(step.remapper, 'prepare_map', prepare_map)
    monkeypatch.chdir(tmp_path)

    step.runtime_setup()

    # the command alone, with the launcher left to the framework
    assert step.args == [['mbtempest', '--file', 'map.nc']]
    assert step.remapper.map_tool == 'moab'
    assert step.remapper.ntasks == 4
    # absolute, since other steps use the remapper from their own directories
    assert step.remapper.map_filename == str(tmp_path / 'map.nc')
    assert step.remapper.src_grid_info['filename'] == str(tmp_path / 'mesh.nc')
