from configparser import ConfigParser

from polaris import provenance
from polaris.build.omega import detect_omega_build_type


def test_detect_omega_build_type_from_omega_cache(tmp_path):
    build_dir = tmp_path / 'build'
    _make_omega_build_dir(build_dir, 'Debug')

    assert detect_omega_build_type(str(build_dir)) == 'Debug'


def test_detect_omega_build_type_from_cmake_build_type(tmp_path):
    build_dir = tmp_path / 'build'
    _make_omega_build_dir(build_dir, 'release', cache_key='CMAKE_BUILD_TYPE')

    assert detect_omega_build_type(str(build_dir)) == 'Release'


def test_provenance_build_type_prefers_omega_cache(tmp_path):
    build_dir = tmp_path / 'build'
    _make_omega_build_dir(build_dir, 'Debug')
    config = _make_config(build_dir, debug=False)

    assert provenance._get_build_type(config) == 'Debug'


def test_provenance_build_type_falls_back_to_config(tmp_path):
    build_dir = tmp_path / 'build'
    build_dir.mkdir()
    config = _make_config(build_dir, debug=True)

    assert provenance._get_build_type(config) == 'Debug'


def test_provenance_write_uses_deploy_pixi_executable(tmp_path, monkeypatch):
    pixi_exe = _make_executable(tmp_path / 'pixi')
    monkeypatch.setenv('MACHE_DEPLOY_ACTIVE_PIXI_EXE', str(pixi_exe))
    monkeypatch.setattr(provenance.sys, 'argv', ['polaris', 'suite'])

    def _check_output(args):
        if args == ['git', 'describe', '--tags', '--dirty', '--always']:
            return b'test-version\n'
        if args == [str(pixi_exe), 'list']:
            return b'test-package\n'
        raise AssertionError(f'unexpected command: {args}')

    monkeypatch.setattr(provenance.subprocess, 'check_output', _check_output)

    provenance.write(str(tmp_path / 'work'), tasks={})

    contents = (tmp_path / 'work' / 'provenance').read_text(encoding='utf-8')
    assert 'pixi list:\n' in contents
    assert 'test-package\n' in contents


def test_provenance_write_skips_pixi_list_when_pixi_missing(
    tmp_path, monkeypatch
):
    monkeypatch.delenv('MACHE_DEPLOY_ACTIVE_PIXI_EXE', raising=False)
    monkeypatch.delenv('MACHE_DEPLOY_COMPUTE_PIXI_EXE', raising=False)
    monkeypatch.delenv('PIXI', raising=False)
    monkeypatch.setenv('PATH', '')
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    monkeypatch.setattr(provenance.sys, 'argv', ['polaris', 'suite'])

    def _check_output(args):
        if args == ['git', 'describe', '--tags', '--dirty', '--always']:
            return b'test-version\n'
        raise AssertionError(f'unexpected command: {args}')

    monkeypatch.setattr(provenance.subprocess, 'check_output', _check_output)

    provenance.write(str(tmp_path / 'work'), tasks={})

    contents = (tmp_path / 'work' / 'provenance').read_text(encoding='utf-8')
    assert 'pixi list:\n' not in contents


def test_get_pixi_executable_falls_back_to_home_default(tmp_path, monkeypatch):
    monkeypatch.delenv('MACHE_DEPLOY_ACTIVE_PIXI_EXE', raising=False)
    monkeypatch.delenv('MACHE_DEPLOY_COMPUTE_PIXI_EXE', raising=False)
    monkeypatch.delenv('PIXI', raising=False)
    monkeypatch.setenv('PATH', '')
    monkeypatch.setenv('HOME', str(tmp_path))

    pixi_exe = _make_executable(tmp_path / '.pixi' / 'bin' / 'pixi')

    assert provenance._get_pixi_executable() == str(pixi_exe)


def _make_omega_build_dir(build_dir, build_type, cache_key='OMEGA_BUILD_TYPE'):
    build_dir.mkdir()
    (build_dir / 'omega_build.sh').write_text('#!/bin/sh\n', encoding='utf-8')
    (build_dir / 'CMakeCache.txt').write_text(
        f'{cache_key}:STRING={build_type}\n', encoding='utf-8'
    )


def _make_config(build_dir, debug):
    config = ConfigParser()
    config.add_section('ocean')
    config.set('ocean', 'model', 'omega')
    config.add_section('paths')
    config.set('paths', 'component_path', str(build_dir))
    config.add_section('build')
    config.set('build', 'debug', str(debug))
    return config


def _make_executable(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('#!/bin/sh\n', encoding='utf-8')
    path.chmod(0o755)
    return path
