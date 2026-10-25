import pytest

from polaris.build.mpas_ocean import make_build_script


@pytest.mark.parametrize('debug', [True, False])
def test_make_build_script_debug_flag(tmp_path, monkeypatch, debug):
    script = _make_script(tmp_path, monkeypatch, debug=debug)

    make_lines = [line for line in script.splitlines() if 'gfortran' in line]
    assert len(make_lines) == 1
    # the MPAS Makefile only builds in debug mode for exactly DEBUG=true
    assert ('DEBUG=true' in make_lines[0].split()) == debug
    assert 'debug=TRUE' not in script


def _make_script(tmp_path, monkeypatch, debug):
    monkeypatch.setenv('POLARIS_BRANCH', str(tmp_path / 'polaris'))
    monkeypatch.setenv('POLARIS_LOAD_SCRIPT', str(tmp_path / 'load.sh'))
    build_dir = tmp_path / 'build'
    build_dir.mkdir()
    script_filename = make_build_script(
        machine='chrysalis',
        compiler='gnu',
        mpilib='openmpi',
        branch=str(tmp_path / 'E3SM'),
        build_dir=str(build_dir),
        debug=debug,
        clean=False,
        make_flags=None,
        make_target='gfortran',
    )
    with open(script_filename, 'r', encoding='utf-8') as f:
        return f.read()
