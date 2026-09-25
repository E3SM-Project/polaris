import subprocess
from configparser import ConfigParser

from polaris import provenance
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


def test_component_git_version_from_branch(tmp_path):
    branch = _make_repo(tmp_path / 'omega', tag='omega-1.0')
    config = _make_config(tmp_path / 'build', branch)

    assert provenance._get_component_git_version(config) == 'omega-1.0'


def test_component_git_version_skips_uninitialized_submodule(tmp_path):
    polaris_dir = _make_repo(tmp_path / 'polaris', tag='polaris-1.0')
    branch = polaris_dir / 'e3sm_submodules' / 'Omega'
    branch.mkdir(parents=True)
    config = _make_config(tmp_path / 'build', branch)

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


def _make_repo(path, tag):
    path.mkdir(parents=True)
    (path / 'README').write_text('test\n', encoding='utf-8')
    _git(path, 'init', '-q')
    _git(path, 'add', 'README')
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


def _make_config(build_dir, branch):
    config = ConfigParser()
    config.add_section('paths')
    config.set('paths', 'component_path', str(build_dir))
    config.add_section('build')
    config.set('build', 'branch', str(branch))
    return config
