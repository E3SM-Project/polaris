import subprocess
from configparser import ConfigParser

from polaris import provenance
from polaris.build.mpas_ocean import (
    get_mpas_ocean_source_dir,
    make_build_script,
)
from polaris.build.omega import get_omega_source_dir


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

    assert provenance._get_component_git_version(config) == 'omega-1.0'


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

    assert provenance._get_component_git_version(config) == 'omega-1.0'


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

    assert provenance._get_component_git_version(config) == 'omega-1.0'


def test_component_git_version_from_mpas_ocean_in_place(tmp_path):
    source_dir = _make_mpas_ocean_source(tmp_path / 'e3sm')
    branch = _make_repo(tmp_path / 'submodule', tag='submodule-1.0')
    config = _make_config(source_dir, branch)

    assert provenance._get_component_git_version(config) == 'e3sm-1.0'


def test_component_git_version_from_mpas_ocean_build(tmp_path, monkeypatch):
    e3sm_dir = tmp_path / 'e3sm'
    _make_mpas_ocean_source(e3sm_dir)
    build_dir = _make_mpas_ocean_build_dir(tmp_path, e3sm_dir, monkeypatch)
    branch = _make_repo(tmp_path / 'submodule', tag='submodule-1.0')
    config = _make_config(build_dir, branch)

    assert provenance._get_component_git_version(config) == 'e3sm-1.0'


def test_component_git_version_missing_mpas_ocean_source(
    tmp_path, monkeypatch
):
    build_dir = _make_mpas_ocean_build_dir(
        tmp_path, tmp_path / 'e3sm', monkeypatch
    )
    branch = _make_repo(tmp_path / 'submodule', tag='submodule-1.0')
    config = _make_config(build_dir, branch)

    assert provenance._get_component_git_version(config) is None


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
