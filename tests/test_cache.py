"""
Unit tests for ``polaris cache``.
"""

import json
import os
import pickle

import pytest

from polaris.cache import update_cache


class _FakeComponent:
    def __init__(self, name):
        self.name = name


class _FakeStep:
    """The handful of attributes update_cache() reads off a step."""

    def __init__(self, component_name, path, outputs):
        self.component = _FakeComponent(component_name)
        self.path = path
        self.outputs = outputs


def _make_step(tmp_path, component_name, step_path, outputs):
    """Pickle a stand-in step the way a run directory would have it."""
    step = _FakeStep(component_name, step_path, outputs)

    pickle_dir = tmp_path / step_path
    pickle_dir.mkdir(parents=True, exist_ok=True)
    with open(pickle_dir / 'step.pickle', 'wb') as handle:
        pickle.dump(step, handle)
    return str(pickle_dir)


@pytest.fixture
def in_tmp_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('POLARIS_MACHINE', 'chrysalis')
    return tmp_path


def test_each_component_gets_its_own_json(in_tmp_cwd):
    """Caching two components writes two files, each named for its own.

    ``out_filename`` used to be computed once, outside the per-component
    loop, from whichever component the *preceding* loop left bound.  Both
    components' entries then landed in a single file named after one of them.
    """
    tmp_path = in_tmp_cwd
    paths = [
        _make_step(tmp_path, 'ocean', 'ocean/step_a', ['ocean/step_a/out.nc']),
        _make_step(tmp_path, 'mesh', 'mesh/step_b', ['mesh/step_b/out.nc']),
    ]

    update_cache(step_paths=paths, date_string='260807', dry_run=True)

    assert os.path.exists('ocean_cached_files.json')
    assert os.path.exists('mesh_cached_files.json')

    with open('ocean_cached_files.json') as f:
        ocean = json.load(f)
    with open('mesh_cached_files.json') as f:
        mesh = json.load(f)

    assert 'ocean/step_a/out.nc' in ocean
    assert 'mesh/step_b/out.nc' not in ocean
    assert 'mesh/step_b/out.nc' in mesh
    assert 'ocean/step_a/out.nc' not in mesh


def test_entry_maps_to_a_date_stamped_target(in_tmp_cwd):
    tmp_path = in_tmp_cwd
    paths = [
        _make_step(
            tmp_path, 'ocean', 'ocean/topo/step', ['ocean/topo/step/out.nc']
        )
    ]

    update_cache(step_paths=paths, date_string='260807', dry_run=True)

    with open('ocean_cached_files.json') as f:
        cached = json.load(f)

    assert cached['ocean/topo/step/out.nc'] == 'topo/step/out.260807.nc'


def test_json_ends_with_a_newline(in_tmp_cwd):
    """json.dump writes none, so every generated file needed one by hand."""
    tmp_path = in_tmp_cwd
    paths = [
        _make_step(tmp_path, 'ocean', 'ocean/step', ['ocean/step/out.nc'])
    ]

    update_cache(step_paths=paths, date_string='260807', dry_run=True)

    with open('ocean_cached_files.json') as f:
        assert f.read().endswith('}\n')


def test_caching_requires_chrysalis(monkeypatch):
    monkeypatch.delenv('POLARIS_MACHINE', raising=False)

    with pytest.raises(ValueError, match='must cache files from Chrysalis'):
        update_cache(step_paths=[], dry_run=True)
