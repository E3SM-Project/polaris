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
