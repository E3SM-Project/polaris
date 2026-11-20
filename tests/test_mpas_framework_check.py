import os
import subprocess

import pytest

from polaris.build.mpas_framework import get_framework_check

OCEAN_CONFIG = dict(core='ocean', compiler='gnu', target='gfortran')


def test_first_build_needs_no_clean(tmp_path):
    e3sm_dir = _make_checkout(tmp_path)

    assert not _needs_clean(e3sm_dir, 'mpas-ocean', OCEAN_CONFIG)


def test_clean_build_is_clean(tmp_path):
    e3sm_dir = _make_checkout(tmp_path)

    assert _needs_clean(e3sm_dir, 'mpas-ocean', OCEAN_CONFIG, clean=True)


def test_same_build_needs_no_clean(tmp_path):
    e3sm_dir = _make_checkout(tmp_path)
    _record_build(e3sm_dir, 'mpas-ocean', OCEAN_CONFIG)

    assert not _needs_clean(e3sm_dir, 'mpas-ocean', OCEAN_CONFIG)


def test_another_compiler_needs_clean(tmp_path):
    e3sm_dir = _make_checkout(tmp_path)
    _record_build(e3sm_dir, 'mpas-ocean', OCEAN_CONFIG)
    config = dict(OCEAN_CONFIG, compiler='intel', target='ifort')

    assert _needs_clean(e3sm_dir, 'mpas-ocean', config)


def test_another_component_needs_clean(tmp_path):
    e3sm_dir = _make_checkout(tmp_path)
    _record_build(e3sm_dir, 'mpas-ocean', OCEAN_CONFIG)
    landice_config = dict(OCEAN_CONFIG, core='landice')

    assert _needs_clean(e3sm_dir, 'mpas-albany-landice', landice_config)


def test_switching_back_needs_clean(tmp_path):
    e3sm_dir = _make_checkout(tmp_path)
    landice_config = dict(OCEAN_CONFIG, core='landice')
    _record_build(e3sm_dir, 'mpas-ocean', OCEAN_CONFIG)
    _record_build(e3sm_dir, 'mpas-albany-landice', landice_config)

    assert _needs_clean(e3sm_dir, 'mpas-ocean', OCEAN_CONFIG)


def test_build_outside_polaris_needs_clean(tmp_path):
    e3sm_dir = _make_checkout(tmp_path)
    _write_core_marker(e3sm_dir, 'mpas-ocean', 'ocean')

    assert _needs_clean(e3sm_dir, 'mpas-ocean', OCEAN_CONFIG)


def test_newer_build_of_another_component_needs_clean(tmp_path):
    e3sm_dir = _make_checkout(tmp_path)
    _record_build(e3sm_dir, 'mpas-ocean', OCEAN_CONFIG)
    # another component was built since, outside of Polaris
    _write_core_marker(e3sm_dir, 'mpas-albany-landice', 'landice', delay=10)

    assert _needs_clean(e3sm_dir, 'mpas-ocean', OCEAN_CONFIG)


def _make_checkout(tmp_path):
    e3sm_dir = tmp_path / 'e3sm'
    for subdir in ['mpas-framework/src', 'mpas-ocean', 'mpas-albany-landice']:
        (e3sm_dir / 'components' / subdir).mkdir(parents=True)
    return e3sm_dir


def _check(e3sm_dir, component, config, clean=False):
    return get_framework_check(
        e3sm_base_dir=str(e3sm_dir),
        component_dir=str(e3sm_dir / 'components' / component),
        build_config=config,
        clean=clean,
    )


def _needs_clean(e3sm_dir, component, config, clean=False):
    script = _check(e3sm_dir, component, config, clean)
    script = f'{script}\necho "${{polaris_needs_clean}}"\n'
    output = subprocess.check_output(['bash', '-e', '-c', script])
    value = output.decode('utf-8').strip()
    assert value in ['true', 'false']
    return value == 'true'


def _record_build(e3sm_dir, component, config):
    """Record a build the way the build scripts do after the check"""
    script = _check(e3sm_dir, component, config)
    script = (
        f'{script}\n'
        f'echo "${{polaris_build_config}}" > "${{polaris_build_record}}"\n'
    )
    subprocess.check_call(['bash', '-e', '-c', script])
    _write_core_marker(e3sm_dir, component, config['core'])


def _write_core_marker(e3sm_dir, component, core, delay=0):
    """Write the marker MPAS writes after a successful build"""
    marker = e3sm_dir / 'components' / component / f'.mpas_core_{core}'
    marker.write_text(f'{core}_model\n', encoding='utf-8')
    if delay:
        stat = os.stat(marker)
        os.utime(marker, (stat.st_atime + delay, stat.st_mtime + delay))


@pytest.mark.parametrize('clean', [False, True])
def test_check_quotes_config(tmp_path, clean):
    e3sm_dir = _make_checkout(tmp_path)
    config = dict(OCEAN_CONFIG, flags='-j 8 DEBUG=true')

    script = _check(e3sm_dir, 'mpas-ocean', config, clean)

    assert "polaris_build_config='core=ocean" in script
    assert 'flags=-j 8 DEBUG=true' in script
