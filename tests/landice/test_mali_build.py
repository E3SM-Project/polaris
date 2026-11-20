import subprocess
from configparser import ConfigParser
from pathlib import Path

import pytest

from polaris import provenance
from polaris.build.mali import (
    build_mali,
    environment_has_albany,
    get_mali_build_albany,
    get_mali_source_dir,
    make_build_script,
)


@pytest.mark.parametrize('albany', [False, True])
def test_build_script_links_albany_only_when_asked(
    tmp_path, monkeypatch, albany
):
    script = _make_script(tmp_path, monkeypatch, albany=albany)
    text = script.read_text(encoding='utf-8')

    assert ('ALBANY=true' in text) == albany
    assert ('${POLARIS_ALBANY_LINK_LIBS}' in text) == albany
    assert f'echo "albany: {str(albany).lower()}"' in text


def test_build_script_builds_in_the_mali_directory(tmp_path, monkeypatch):
    script = _make_script(tmp_path, monkeypatch, albany=False)
    text = script.read_text(encoding='utf-8')

    mali_dir = tmp_path / 'e3sm' / 'components' / 'mpas-albany-landice'
    assert f'cd {mali_dir}\n' in text
    assert _make_command(text).endswith(' gfortran')
    # MALI's optional submodules are not initialized
    assert 'git submodule update' not in text
    for filename in [
        'default_inputs/namelist.landice',
        'default_inputs/streams.landice',
        'src/Registry_processed.xml',
        'landice_model',
    ]:
        assert f'{mali_dir}/{filename}' in text


def test_build_script_debug_flag(tmp_path, monkeypatch):
    script = _make_script(tmp_path, monkeypatch, albany=False, debug=True)
    text = script.read_text(encoding='utf-8')

    # the MPAS Makefile reads DEBUG, not debug
    assert _make_command(text).startswith('make  DEBUG=true ')


@pytest.mark.parametrize('albany', [False, True])
def test_build_script_links_to_the_spack_view(tmp_path, monkeypatch, albany):
    script = _make_script(tmp_path, monkeypatch, albany=albany)
    text = script.read_text(encoding='utf-8')

    # netCDF and PnetCDF in the Spack view are found at run time on machines
    # where no module puts them on the library path
    assert '-Wl,-rpath,${MACHE_DEPLOY_SPACK_LIBRARY_VIEW}/lib' in text
    assert '${polaris_view_rpath}' in _make_command(text)


def test_build_script_initializes_the_mali_dev_submodule(
    tmp_path, monkeypatch
):
    branch = tmp_path / 'polaris' / 'e3sm_submodules' / 'MALI-Dev'
    script = _make_script(tmp_path, monkeypatch, albany=False, branch=branch)
    text = script.read_text(encoding='utf-8')

    assert 'git submodule update --init e3sm_submodules/MALI-Dev' in text


def test_environment_has_albany(monkeypatch):
    monkeypatch.delenv('POLARIS_ALBANY_LINK_LIBS', raising=False)
    assert not environment_has_albany()

    monkeypatch.setenv('POLARIS_ALBANY_LINK_LIBS', '-lalbany')
    assert environment_has_albany()


def test_build_with_albany_needs_albany_environment(tmp_path, monkeypatch):
    monkeypatch.setenv('POLARIS_MACHINE', 'chrysalis')
    monkeypatch.setenv('POLARIS_COMPILER', 'gnu')
    monkeypatch.setenv('POLARIS_MPI', 'openmpi')
    monkeypatch.delenv('POLARIS_ALBANY_LINK_LIBS', raising=False)

    with pytest.raises(ValueError, match='--with-albany'):
        build_mali(
            branch=str(tmp_path / 'e3sm'),
            build_dir=str(tmp_path / 'build'),
            clean=False,
            quiet=True,
            debug=False,
            make_flags=None,
            make_target='gfortran',
            albany=True,
        )


@pytest.mark.parametrize('albany', [False, True])
def test_source_record_says_whether_build_has_albany(
    tmp_path, monkeypatch, albany
):
    e3sm_dir = _make_repo(tmp_path / 'e3sm')
    script = _make_script(tmp_path, monkeypatch, albany=albany)
    _run_source_record_block(script, e3sm_dir)

    build_dir = str(tmp_path / 'build')
    assert get_mali_build_albany(build_dir) is albany
    assert get_mali_source_dir(build_dir) == str(
        e3sm_dir / 'components' / 'mpas-albany-landice'
    )


def test_build_without_record(tmp_path):
    build_dir = tmp_path / 'build'
    build_dir.mkdir()

    assert get_mali_build_albany(str(build_dir)) is None
    assert get_mali_source_dir(str(build_dir)) is None


def test_get_mali_source_dir_in_place(tmp_path):
    source_dir = tmp_path / 'e3sm' / 'components' / 'mpas-albany-landice'
    (source_dir / 'src').mkdir(parents=True)
    (source_dir / 'src' / 'Registry.xml').write_text(
        '<registry/>\n', encoding='utf-8'
    )

    assert get_mali_source_dir(str(source_dir)) == str(source_dir)


def test_provenance_model_for_landice():
    config = ConfigParser()
    config.add_section('landice')
    config.set('landice', 'model', 'mali')

    assert provenance._get_model(config) == 'mali'


def _make_script(tmp_path, monkeypatch, albany, debug=False, branch=None):
    """The build script Polaris writes to build MALI"""
    monkeypatch.setenv('POLARIS_BRANCH', str(tmp_path / 'polaris'))
    monkeypatch.setenv('POLARIS_LOAD_SCRIPT', str(tmp_path / 'load.sh'))
    if branch is None:
        branch = tmp_path / 'e3sm'
    build_dir = tmp_path / 'build'
    build_dir.mkdir(exist_ok=True)
    script = make_build_script(
        machine='chrysalis',
        compiler='gnu',
        mpilib='openmpi',
        branch=str(branch),
        build_dir=str(build_dir),
        debug=debug,
        clean=False,
        make_flags=None,
        make_target='gfortran',
        albany=albany,
    )
    return Path(script)


def _make_repo(path):
    path.mkdir(parents=True)
    (path / 'README').write_text('test\n', encoding='utf-8')
    for args in [
        ['init', '-q'],
        ['add', '.'],
        ['commit', '-q', '-m', 'Initial commit'],
    ]:
        subprocess.check_call(
            [
                'git',
                '-c',
                'user.name=Test',
                '-c',
                'user.email=test@example.com',
                *args,
            ],
            cwd=path,
        )
    return path


def _run_source_record_block(script, cwd):
    """
    Run the lines of a build script that write the source record, which
    end with the redirect to the record and start after a blank line
    """
    with open(script, 'r', encoding='utf-8') as f:
        lines = f.read().splitlines()
    end = next(
        index for index, line in enumerate(lines) if line.startswith('} > ')
    )
    start = end
    while lines[start - 1].strip() != '':
        start -= 1
    block = '\n'.join(lines[start : end + 1])
    subprocess.check_call(['bash', '-e', '-c', block], cwd=cwd)


def _make_command(text):
    """
    The build script's make command, with its continued lines joined
    """
    lines = text.splitlines()
    index = next(
        index for index, line in enumerate(lines) if line.startswith('make ')
    )
    command = ''
    for line in lines[index:]:
        if not line.endswith('\\'):
            return command + line.strip()
        command += line[:-1].lstrip() if command else line[:-1]
    return command
