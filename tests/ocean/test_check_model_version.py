import textwrap
import warnings
from configparser import ConfigParser

import pytest

from polaris.constants.pcd import get_pcd_version
from polaris.tasks.ocean import Ocean


def test_check_uses_branch_being_built(tmp_path):
    old_branch = _make_branch(tmp_path / 'old', version='999.999.999')
    build_dir = _make_mpas_ocean_build(tmp_path / 'build', old_branch)
    branch = _make_branch(tmp_path / 'new', version=get_pcd_version())
    config = _make_config('mpas-ocean', build_dir, branch, build=True)

    Ocean().check_model_version(config)


def test_check_uses_mpas_ocean_build_branch(tmp_path):
    built_branch = _make_branch(tmp_path / 'fanssie', version='999.999.999')
    build_dir = _make_mpas_ocean_build(tmp_path / 'build', built_branch)
    default_branch = _make_branch(tmp_path / 'e3sm', version=get_pcd_version())
    config = _make_config('mpas-ocean', build_dir, default_branch)

    with pytest.raises(ValueError, match=str(built_branch)):
        Ocean().check_model_version(config)


def test_check_uses_mpas_ocean_in_place_build_branch(tmp_path):
    built_branch = _make_branch(tmp_path / 'fanssie', version='999.999.999')
    source_dir = built_branch / 'components' / 'mpas-ocean'
    _make_mpas_ocean_build_files(source_dir)
    (source_dir / 'src' / 'Registry.xml').write_text('', encoding='utf-8')
    default_branch = _make_branch(tmp_path / 'e3sm', version=get_pcd_version())
    config = _make_config('mpas-ocean', source_dir, default_branch)

    with pytest.raises(ValueError, match=str(built_branch)):
        Ocean().check_model_version(config)


def test_check_uses_omega_build_branch(tmp_path):
    built_branch = _make_branch(tmp_path / 'omega', version='999.999.999')
    build_dir = tmp_path / 'build'
    (build_dir / 'configs').mkdir(parents=True)
    (build_dir / 'src').mkdir()
    (build_dir / 'configs' / 'Default.yml').write_text('', encoding='utf-8')
    (build_dir / 'src' / 'omega.exe').write_text('', encoding='utf-8')
    source_dir = built_branch / 'components' / 'omega'
    (build_dir / 'CMakeCache.txt').write_text(
        f'CMAKE_HOME_DIRECTORY:INTERNAL={source_dir}\n', encoding='utf-8'
    )
    default_branch = _make_branch(tmp_path / 'e3sm', version=get_pcd_version())
    config = _make_config('omega', build_dir, default_branch)

    with pytest.raises(ValueError, match=str(built_branch)):
        Ocean().check_model_version(config)


def test_check_warns_without_build_source(tmp_path):
    build_dir = tmp_path / 'build'
    _make_mpas_ocean_build_files(build_dir)
    default_branch = _make_branch(tmp_path / 'e3sm', version=get_pcd_version())
    config = _make_config('mpas-ocean', build_dir, default_branch)

    with pytest.warns(UserWarning, match='could not be determined'):
        Ocean().check_model_version(config)


def test_check_skipped_without_build(tmp_path):
    default_branch = _make_branch(tmp_path / 'e3sm', version='999.999.999')
    config = _make_config('mpas-ocean', tmp_path / 'build', default_branch)

    with warnings.catch_warnings():
        warnings.simplefilter('error')
        Ocean().check_model_version(config)


def _make_branch(branch_dir, version):
    share_dir = branch_dir / 'share'
    share_dir.mkdir(parents=True)
    (share_dir / 'pcd.yaml').write_text(
        textwrap.dedent(
            f"""
            physical_constants_dictionary:
              version_number: {version}
              set: []
            """
        ).strip()
        + '\n',
        encoding='utf-8',
    )
    return branch_dir


def _make_mpas_ocean_build(build_dir, branch):
    """A build directory as Polaris's MPAS-Ocean build script leaves it"""
    _make_mpas_ocean_build_files(build_dir)
    source_dir = branch / 'components' / 'mpas-ocean'
    (build_dir / 'build_mpas_ocean_chrysalis_gnu_openmpi.sh').write_text(
        f'#!/usr/bin/env bash\ncd {source_dir}\nmake gfortran\n',
        encoding='utf-8',
    )
    return build_dir


def _make_mpas_ocean_build_files(build_dir):
    for filename in [
        'default_inputs/namelist.ocean.forward',
        'default_inputs/streams.ocean.forward',
        'src/Registry_processed.xml',
        'ocean_model',
    ]:
        path = build_dir / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('', encoding='utf-8')


def _make_config(model, build_dir, branch, build=False):
    config = ConfigParser()
    config.add_section('ocean')
    config.set('ocean', 'model', model)
    config.add_section('paths')
    config.set('paths', 'component_path', str(build_dir))
    config.add_section('build')
    config.set('build', 'build', str(build))
    config.set('build', 'branch', str(branch))
    return config
