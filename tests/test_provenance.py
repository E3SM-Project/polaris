import subprocess
from configparser import ConfigParser

from polaris import provenance
from polaris.build.mpas_ocean import (
    get_mpas_ocean_source_dir,
    make_build_script,
)
from polaris.build.omega import get_omega_source_dir
from polaris.build.omega import make_build_script as make_omega_build_script
from polaris.build.source_record import read_source_record
from polaris.run.serial import _parse_provenance_into


def test_get_omega_source_dir_from_cmake_cache(tmp_path):
    source_dir = tmp_path / 'omega' / 'components' / 'omega'
    build_dir = _make_omega_build_dir(tmp_path / 'build', source_dir)

    assert get_omega_source_dir(str(build_dir)) == str(source_dir)


def test_get_omega_source_dir_needs_omega_build(tmp_path):
    build_dir = tmp_path / 'build'
    build_dir.mkdir()
    (build_dir / 'CMakeCache.txt').write_text(
        f'CMAKE_HOME_DIRECTORY:INTERNAL={tmp_path}\n', encoding='utf-8'
    )

    assert get_omega_source_dir(str(build_dir)) is None


def test_get_mpas_ocean_source_dir_in_place(tmp_path):
    source_dir = _make_mpas_ocean_source(tmp_path / 'e3sm')

    assert get_mpas_ocean_source_dir(str(source_dir)) == str(source_dir)


def test_get_mpas_ocean_source_dir_from_build_script(tmp_path, monkeypatch):
    e3sm_dir = tmp_path / 'e3sm'
    build_dir = _make_mpas_ocean_build_dir(tmp_path, e3sm_dir, monkeypatch)

    assert get_mpas_ocean_source_dir(str(build_dir)) == str(
        e3sm_dir / 'components' / 'mpas-ocean'
    )


def test_get_mpas_ocean_source_dir_needs_mpas_ocean_build(tmp_path):
    build_dir = tmp_path / 'build'
    build_dir.mkdir()

    assert get_mpas_ocean_source_dir(str(build_dir)) is None


def test_component_git_version_from_branch(tmp_path):
    branch = _make_repo(tmp_path / 'omega', tag='omega-1.0')
    config = _make_config(tmp_path / 'build', branch, build=True)

    assert provenance._get_component_git_version(config) == (
        'omega-1.0 (at setup, not build)'
    )


def test_component_git_version_skips_uninitialized_submodule(tmp_path):
    polaris_dir = _make_repo(tmp_path / 'polaris', tag='polaris-1.0')
    branch = polaris_dir / 'e3sm_submodules' / 'Omega'
    branch.mkdir(parents=True)
    config = _make_config(tmp_path / 'build', branch, build=True)

    assert provenance._get_component_git_version(config) is None


def test_component_git_version_from_omega_build(tmp_path):
    omega_dir = _make_repo(tmp_path / 'omega', tag='omega-1.0')
    source_dir = omega_dir / 'components' / 'omega'
    source_dir.mkdir(parents=True)
    build_dir = _make_omega_build_dir(tmp_path / 'build', source_dir)
    # the branch is a different checkout that the build did not use
    branch = _make_repo(tmp_path / 'submodule', tag='submodule-1.0')
    config = _make_config(build_dir, branch)

    assert provenance._get_component_git_version(config) == (
        'omega-1.0 (at setup, not build)'
    )


def test_component_git_version_missing_build_source(tmp_path):
    source_dir = tmp_path / 'omega' / 'components' / 'omega'
    build_dir = _make_omega_build_dir(tmp_path / 'build', source_dir)
    branch = _make_repo(tmp_path / 'submodule', tag='submodule-1.0')
    config = _make_config(build_dir, branch)

    assert provenance._get_component_git_version(config) is None


def test_component_git_version_ignores_branch_when_not_building(tmp_path):
    branch = _make_repo(tmp_path / 'omega', tag='omega-1.0')
    config = _make_config(tmp_path / 'build', branch)

    assert provenance._get_component_git_version(config) is None


def test_component_git_version_building_over_old_build(tmp_path):
    old_dir = _make_repo(tmp_path / 'old', tag='old-1.0')
    source_dir = old_dir / 'components' / 'omega'
    source_dir.mkdir(parents=True)
    build_dir = _make_omega_build_dir(tmp_path / 'build', source_dir)
    branch = _make_repo(tmp_path / 'omega', tag='omega-1.0')
    config = _make_config(build_dir, branch, build=True)

    assert provenance._get_component_git_version(config) == (
        'omega-1.0 (at setup, not build)'
    )


def test_component_git_version_from_mpas_ocean_in_place(tmp_path):
    source_dir = _make_mpas_ocean_source(tmp_path / 'e3sm')
    branch = _make_repo(tmp_path / 'submodule', tag='submodule-1.0')
    config = _make_config(source_dir, branch)

    assert provenance._get_component_git_version(config) == (
        'e3sm-1.0 (at setup, not build)'
    )


def test_component_git_version_from_mpas_ocean_build(tmp_path, monkeypatch):
    e3sm_dir = tmp_path / 'e3sm'
    _make_mpas_ocean_source(e3sm_dir)
    build_dir = _make_mpas_ocean_build_dir(tmp_path, e3sm_dir, monkeypatch)
    branch = _make_repo(tmp_path / 'submodule', tag='submodule-1.0')
    config = _make_config(build_dir, branch)

    assert provenance._get_component_git_version(config) == (
        'e3sm-1.0 (at setup, not build)'
    )


def test_component_git_version_missing_mpas_ocean_source(
    tmp_path, monkeypatch
):
    build_dir = _make_mpas_ocean_build_dir(
        tmp_path, tmp_path / 'e3sm', monkeypatch
    )
    branch = _make_repo(tmp_path / 'submodule', tag='submodule-1.0')
    config = _make_config(build_dir, branch)

    assert provenance._get_component_git_version(config) is None


def test_omega_build_script_records_source(tmp_path, monkeypatch):
    omega_dir = _make_repo(tmp_path / 'omega', tag='omega-1.0')
    build_dir = tmp_path / 'build'
    script = _make_omega_build_script(tmp_path, omega_dir, monkeypatch)

    _run_source_record_block(script, build_dir)
    record = read_source_record(str(build_dir))
    assert record is not None
    assert record['source'] == str(omega_dir)
    assert record['hash'] == _git_output(omega_dir, 'rev-parse', 'HEAD')
    assert record['describe'] == 'omega-1.0'
    assert record['clean_build'] is True
    assert len(record['log']) == 1
    assert record['log'][0].endswith(' Initial commit')

    # an incremental build does not start from an empty build directory
    (build_dir / 'CMakeCache.txt').write_text('', encoding='utf-8')
    _run_source_record_block(script, build_dir)
    record = read_source_record(str(build_dir))
    assert record is not None
    assert record['clean_build'] is False


def test_component_git_version_from_omega_record(tmp_path, monkeypatch):
    omega_dir = _make_repo(tmp_path / 'omega', tag='omega-1.0')
    source_dir = omega_dir / 'components' / 'omega'
    source_dir.mkdir(parents=True)
    build_dir = _make_omega_build_dir(tmp_path / 'build', source_dir)
    script = _make_omega_build_script(tmp_path, omega_dir, monkeypatch)
    _run_source_record_block(script, build_dir)
    # the source tree moves on after the build
    _commit(omega_dir, tag='omega-2.0')
    branch = _make_repo(tmp_path / 'submodule', tag='submodule-1.0')

    config = _make_config(build_dir, branch)
    assert provenance._get_component_git_version(config) == 'omega-1.0'

    # the record is also preferred once Polaris has built the branch
    config = _make_config(build_dir, branch, build=True)
    assert provenance._get_component_git_version(config) == 'omega-1.0'


def test_component_git_version_from_mpas_ocean_record(tmp_path, monkeypatch):
    e3sm_dir = tmp_path / 'e3sm'
    _make_mpas_ocean_source(e3sm_dir)
    build_dir = _make_mpas_ocean_build_dir(tmp_path, e3sm_dir, monkeypatch)
    (script,) = build_dir.glob('build_mpas_ocean_*.sh')
    _run_source_record_block(script, e3sm_dir / 'components' / 'mpas-ocean')
    _commit(e3sm_dir, tag='e3sm-2.0')
    branch = _make_repo(tmp_path / 'submodule', tag='submodule-1.0')
    config = _make_config(build_dir, branch)

    record = read_source_record(str(build_dir))
    assert record is not None
    assert record['source'] == str(e3sm_dir)
    assert record['clean_build'] is False
    assert provenance._get_component_git_version(config) == 'e3sm-1.0'


def test_write_git_entries_from_record(tmp_path, monkeypatch):
    polaris_dir = _make_polaris_checkout(tmp_path, monkeypatch)
    omega_dir = _make_repo(tmp_path / 'omega', tag='omega-1.0')
    source_dir = omega_dir / 'components' / 'omega'
    source_dir.mkdir(parents=True)
    build_dir = _make_omega_build_dir(tmp_path / 'build', source_dir)
    script = _make_omega_build_script(tmp_path, omega_dir, monkeypatch)
    _run_source_record_block(script, build_dir)
    omega_hash = _git_output(omega_dir, 'rev-parse', 'HEAD')
    _commit(omega_dir, tag='omega-2.0')
    config = _make_config(build_dir, omega_dir)

    work_dir = tmp_path / 'work'
    provenance.write(str(work_dir), {}, config=config, machine='chrysalis')
    text = (work_dir / 'provenance').read_text(encoding='utf-8')

    polaris_hash = _git_output(polaris_dir, 'rev-parse', 'HEAD')
    polaris_log = _git_output(
        polaris_dir, 'log', '--first-parent', '--format=%h %s'
    )
    polaris_log = '\n'.join(f'  {line}' for line in polaris_log.splitlines())
    omega_short = _git_output(omega_dir, 'rev-parse', '--short', 'omega-1.0')
    assert f'polaris git hash: {polaris_hash}\n' in text
    assert f'polaris git log:\n{polaris_log}\n\n' in text
    assert f'component git hash: {omega_hash}\n' in text
    assert f'component git log:\n  {omega_short} Initial commit\n\n' in text

    values = _parse_one_line_keys(work_dir / 'provenance')
    assert values['polaris git version'] == 'polaris-2.0'
    assert values['component git version'] == 'omega-1.0'
    assert values['component git hash'] == omega_hash
    assert values['component git log'] == ''
    # a commit subject on a continuation line is not read as a key
    assert values['machine'] == 'chrysalis'


def test_write_git_entries_at_setup(tmp_path, monkeypatch):
    _make_polaris_checkout(tmp_path, monkeypatch)
    branch = _make_repo(tmp_path / 'omega', tag='omega-1.0')
    config = _make_config(tmp_path / 'build', branch, build=True)

    work_dir = tmp_path / 'work'
    provenance.write(str(work_dir), {}, config=config)

    branch_hash = _git_output(branch, 'rev-parse', 'HEAD')
    values = _parse_one_line_keys(work_dir / 'provenance')
    assert values['component git version'] == (
        'omega-1.0 (at setup, not build)'
    )
    assert values['component git hash'] == (
        f'{branch_hash} (at setup, not build)'
    )
    assert values['component git log'] == '(at setup, not build)'


def test_read_git_entries_from_record(tmp_path, monkeypatch):
    polaris_dir = _make_polaris_checkout(tmp_path, monkeypatch)
    omega_dir = _make_repo(tmp_path / 'omega', tag='omega-1.0')
    source_dir = omega_dir / 'components' / 'omega'
    source_dir.mkdir(parents=True)
    build_dir = _make_omega_build_dir(tmp_path / 'build', source_dir)
    script = _make_omega_build_script(tmp_path, omega_dir, monkeypatch)
    _run_source_record_block(script, build_dir)
    omega_hash = _git_output(omega_dir, 'rev-parse', 'HEAD')
    _commit(omega_dir, tag='omega-2.0')
    config = _make_config(build_dir, omega_dir)
    config.add_section('ocean')
    config.set('ocean', 'model', 'omega')

    work_dir = tmp_path / 'work'
    provenance.write(str(work_dir), {}, config=config, machine='chrysalis')
    values = provenance.read(str(work_dir))
    assert values is not None

    polaris_log = _git_output(
        polaris_dir, 'log', '--first-parent', '--format=%h %s'
    )
    omega_short = _git_output(omega_dir, 'rev-parse', '--short', 'omega-1.0')
    assert values['polaris'] == {
        'describe': 'polaris-2.0',
        'hash': _git_output(polaris_dir, 'rev-parse', 'HEAD'),
        'log': polaris_log.splitlines(),
        'at_setup': False,
    }
    assert values['component'] == {
        'describe': 'omega-1.0',
        'hash': omega_hash,
        'log': [f'{omega_short} Initial commit'],
        'at_setup': False,
    }
    # a commit subject in a log is not read as a key
    assert values['machine'] == 'chrysalis'
    assert values['model'] == 'omega'
    assert values['build directory'] == str(build_dir)


def test_read_git_entries_at_setup(tmp_path, monkeypatch):
    _make_polaris_checkout(tmp_path, monkeypatch)
    branch = _make_repo(tmp_path / 'omega', tag='omega-1.0')
    config = _make_config(tmp_path / 'build', branch, build=True)

    work_dir = tmp_path / 'work'
    provenance.write(str(work_dir), {}, config=config)
    values = provenance.read(str(work_dir))
    assert values is not None
    component = values['component']

    assert component['describe'] == 'omega-1.0'
    assert component['hash'] == _git_output(branch, 'rev-parse', 'HEAD')
    assert component['at_setup']


def test_read_stops_at_tasks(tmp_path):
    (tmp_path / 'provenance').write_text(
        'polaris git version: polaris-1.0\n\n'
        'machine: chrysalis\n\n'
        'tasks:\n'
        '  path:          ocean/planar/merry_go_round/default\n'
        'pixi list:\n'
        'Environment: default\n',
        encoding='utf-8',
    )

    values = provenance.read(str(tmp_path))

    assert values is not None
    assert values['polaris']['describe'] == 'polaris-1.0'
    assert values['component'] is None
    assert values['machine'] == 'chrysalis'
    assert 'path' not in values
    assert 'Environment' not in values


def test_read_without_provenance(tmp_path):
    assert provenance.read(str(tmp_path)) is None


def _make_repo(path, tag, exist_ok=False):
    path.mkdir(parents=True, exist_ok=exist_ok)
    (path / 'README').write_text('test\n', encoding='utf-8')
    _git(path, 'init', '-q')
    _git(path, 'add', '.')
    _git(path, 'commit', '-q', '-m', 'Initial commit')
    _git(path, 'tag', tag)
    return path


def _git(path, *args):
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


def _make_polaris_checkout(tmp_path, monkeypatch):
    """A Polaris checkout to run from, with a subject that looks like a key"""
    polaris_dir = _make_repo(tmp_path / 'polaris', tag='polaris-1.0')
    (polaris_dir / 'CHANGES').write_text('chrysalis\n', encoding='utf-8')
    _git(polaris_dir, 'add', '.')
    _git(polaris_dir, 'commit', '-q', '-m', 'machine: update chrysalis')
    _git(polaris_dir, 'tag', 'polaris-2.0')
    monkeypatch.chdir(polaris_dir)
    monkeypatch.setattr(provenance, '_get_pixi_executable', lambda: None)
    return polaris_dir


def _parse_one_line_keys(path):
    """Read the provenance keys the way ``polaris.run.serial`` does"""
    keys = [
        'polaris git version',
        'polaris git hash',
        'polaris git log',
        'component git version',
        'component git hash',
        'component git log',
        'machine',
    ]
    values: dict[str, str] = dict()
    _parse_provenance_into(str(path), {key: key for key in keys}, values)
    return values


def _commit(path, tag):
    (path / 'CHANGES').write_text(f'{tag}\n', encoding='utf-8')
    _git(path, 'add', '.')
    _git(path, 'commit', '-q', '-m', f'Update to {tag}')
    _git(path, 'tag', tag)


def _git_output(path, *args):
    output = subprocess.check_output(['git', *args], cwd=path)
    return output.decode('utf-8').strip()


def _make_omega_build_script(tmp_path, omega_dir, monkeypatch):
    """The build script Polaris writes to build Omega from omega_dir"""
    monkeypatch.setenv('POLARIS_BRANCH', str(tmp_path / 'polaris'))
    monkeypatch.setenv('METIS_ROOT', str(tmp_path / 'metis'))
    monkeypatch.setenv('PARMETIS_ROOT', str(tmp_path / 'parmetis'))
    build_dir = tmp_path / 'build'
    build_dir.mkdir(exist_ok=True)
    script = make_omega_build_script(
        machine='chrysalis',
        compiler='gnu',
        branch=str(omega_dir),
        build_dir=str(build_dir),
        debug=False,
        cmake_flags=None,
    )
    return script


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


def _make_omega_build_dir(build_dir, source_dir):
    build_dir.mkdir()
    (build_dir / 'omega_build.sh').write_text('#!/bin/sh\n', encoding='utf-8')
    (build_dir / 'CMakeCache.txt').write_text(
        f'CMAKE_HOME_DIRECTORY:INTERNAL={source_dir}\n', encoding='utf-8'
    )
    return build_dir


def _make_mpas_ocean_source(e3sm_dir):
    source_dir = e3sm_dir / 'components' / 'mpas-ocean'
    (source_dir / 'src').mkdir(parents=True)
    (source_dir / 'src' / 'Registry.xml').write_text(
        '<registry/>\n', encoding='utf-8'
    )
    _make_repo(e3sm_dir, tag='e3sm-1.0', exist_ok=True)
    return source_dir


def _make_mpas_ocean_build_dir(tmp_path, e3sm_dir, monkeypatch):
    """A build directory as Polaris's MPAS-Ocean build script leaves it"""
    monkeypatch.setenv('POLARIS_BRANCH', str(tmp_path / 'polaris'))
    monkeypatch.setenv('POLARIS_LOAD_SCRIPT', str(tmp_path / 'load.sh'))
    build_dir = tmp_path / 'build'
    build_dir.mkdir()
    make_build_script(
        machine='chrysalis',
        compiler='gnu',
        mpilib='openmpi',
        branch=str(e3sm_dir),
        build_dir=str(build_dir),
        debug=False,
        clean=False,
        make_flags=None,
        make_target='gfortran',
    )
    return build_dir


def _make_config(build_dir, branch, build=False):
    config = ConfigParser()
    config.add_section('paths')
    config.set('paths', 'component_path', str(build_dir))
    config.add_section('build')
    config.set('build', 'build', str(build))
    config.set('build', 'branch', str(branch))
    return config
