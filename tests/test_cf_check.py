import logging
import os

import numpy as np
import pytest
import xarray as xr

from polaris.cf_check import (
    CF_TABLES,
    check_cf_compliance,
    resolve_cf_check_files,
)
from polaris.component import Component
from polaris.config import PolarisConfigParser
from polaris.ocean.model.ocean_model_step import OceanModelStep
from polaris.run.serial import (
    _cf_check_message,
    _check_step_cf,
    _read_cf_status_from_logs,
    _result_lines,
)
from polaris.step import Step
from polaris.tasks.ocean import Ocean

# minimal versions of the three CF tables, with only what the tests use
STANDARD_NAMES = """<?xml version="1.0"?>
<standard_name_table>
  <version_number>94</version_number>
  <last_modified>2026-06-09T17:23:36Z</last_modified>
  <entry id="sea_water_potential_temperature">
    <canonical_units>K</canonical_units>
  </entry>
  <entry id="sea_surface_height_above_geoid">
    <canonical_units>m</canonical_units>
  </entry>
</standard_name_table>
"""

AREA_TYPES = """<?xml version="1.0"?>
<area_type_table>
  <version_number>13</version_number>
  <date>20 March 2025</date>
  <entry id="sea"/>
</area_type_table>
"""

REGION_NAMES = """<?xml version="1.0"?>
<standardized_region_list>
  <version_number>5</version_number>
  <date>12 November 2024</date>
  <entry id="global_ocean"/>
</standardized_region_list>
"""


@pytest.fixture
def work_dir(tmp_path):
    """A step work directory with the CF tables in it"""
    for (_, filename), contents in zip(
        CF_TABLES, [STANDARD_NAMES, AREA_TYPES, REGION_NAMES], strict=True
    ):
        (tmp_path / filename).write_text(contents)
    return str(tmp_path)


def _write(path, variables, conventions='CF-1.8'):
    """Write a small file whose variables carry the given attributes"""
    data_vars = {}
    for name, attrs in variables.items():
        data_vars[name] = ('nCells', np.zeros(3), attrs)
    ds = xr.Dataset(data_vars)
    if conventions is not None:
        ds.attrs['Conventions'] = conventions
    ds.to_netcdf(path)


def _compliant(path):
    _write(
        path,
        {
            'temperature': dict(
                units='degree_C',
                standard_name='sea_water_potential_temperature',
                long_name='potential temperature',
            ),
            'ssh': dict(units='m', long_name='sea surface height'),
        },
    )


def _noncompliant(path):
    _write(
        path,
        {
            'stress': dict(units='N m^{-2}', long_name='surface stress'),
            'velocity': dict(
                units='m s-1', standard_name='sea_water_velocity'
            ),
        },
    )


def test_resolve_keeps_explicit_files_and_skips_unmatched_patterns(
    tmp_path,
):
    (tmp_path / 'output.nc').touch()
    filenames = resolve_cf_check_files(
        ['output.nc', 'missing.nc', 'restarts/rst.*.nc', 'output.nc'],
        str(tmp_path),
    )
    assert filenames == ['output.nc', 'missing.nc']


def test_resolve_checks_only_the_first_file_of_a_series(tmp_path):
    restarts = tmp_path / 'restarts'
    restarts.mkdir()
    for stamp in ['0001-01-03', '0001-01-01', '0001-01-02']:
        (restarts / f'rst.{stamp}.nc').touch()
    filenames = resolve_cf_check_files(['restarts/rst.*.nc'], str(tmp_path))
    assert filenames == ['restarts/rst.0001-01-01.nc']


def test_resolve_keeps_files_outside_the_work_dir_absolute(tmp_path):
    step_dir = tmp_path / 'step'
    step_dir.mkdir()
    outside = tmp_path / 'restarts' / 'rst.0001-01-01.nc'
    outside.parent.mkdir()
    outside.touch()
    pattern = str(tmp_path / 'restarts' / 'rst.*.nc')
    assert resolve_cf_check_files([pattern], str(step_dir)) == [str(outside)]


def test_compliant_file_passes(work_dir):
    _compliant(os.path.join(work_dir, 'output.nc'))
    results = check_cf_compliance(['output.nc'], work_dir)
    assert len(results) == 1
    result = results[0]
    assert result['passed']
    assert result['errors'] == []
    assert 'output.nc' in result['report']


def test_invalid_units_and_standard_name_are_errors(work_dir):
    _noncompliant(os.path.join(work_dir, 'output.nc'))
    result = check_cf_compliance(['output.nc'], work_dir)[0]
    assert not result['passed']
    assert any(
        error.startswith('stress:') and 'Invalid units' in error
        for error in result['errors']
    )
    assert any(
        error.startswith('velocity:') and 'Invalid standard_name' in error
        for error in result['errors']
    )


def test_missing_conventions_is_only_a_warning(work_dir):
    path = os.path.join(work_dir, 'output.nc')
    _write(
        path,
        {'ssh': dict(units='m', long_name='sea surface height')},
        conventions=None,
    )
    result = check_cf_compliance(['output.nc'], work_dir)[0]
    assert result['passed']
    assert result['warnings'] > 0


def test_missing_file_fails(work_dir):
    result = check_cf_compliance(['missing.nc'], work_dir)[0]
    assert not result['passed']
    assert result['errors'] == ['file not found']


def _step(work_dir):
    step = Step(component=Component(name='ocean'), name='forward')
    step.work_dir = work_dir
    step.logger = logging.getLogger('test_cf_check')
    return step


def test_step_without_check_checks_nothing(work_dir):
    step = _step(work_dir)
    assert step.check_cf() == (False, True)
    step.add_cf_check()
    assert step.cf_check
    assert step.check_cf() == (False, True)


def test_step_checks_its_files(work_dir):
    _compliant(os.path.join(work_dir, 'good.nc'))
    _noncompliant(os.path.join(work_dir, 'bad.nc'))
    step = _step(work_dir)
    step.add_cf_check('good.nc')
    assert step.check_cf() == (True, True)
    step.add_cf_check('bad.nc')
    step.add_cf_check('bad.nc')
    assert step.cf_check_files == ['good.nc', 'bad.nc']
    assert step.check_cf() == (True, False)
    assert [r['filename'] for r in step.cf_check_results] == [
        'good.nc',
        'bad.nc',
    ]


OMEGA_YAML = """Omega:
  IOStreams:
    InitialState:
      Filename: init.nc
      Mode: read
    RestartWrite:
      Filename: {restarts}/ocn.rst.$Y-$M-$D_$h.$m.$s.nc
      Mode: write
    History:
      Filename: output.nc
      Mode: write
"""


def _omega_step(work_dir, model):
    step = OceanModelStep(component=Ocean(), name='forward')
    step.work_dir = work_dir
    step.logger = logging.getLogger('test_cf_check')
    step.yaml = 'omega.yml'
    step.streams_section = 'IOStreams'
    config = PolarisConfigParser()
    config.add_from_package('polaris', 'default.cfg')
    config.add_from_package('polaris.ocean', 'ocean.cfg')
    config.set('ocean', 'model', model)
    step.config = config
    step.add_cf_check()
    return step


def test_omega_step_checks_the_first_file_of_each_write_stream(work_dir):
    restarts = os.path.join(work_dir, 'restarts')
    os.makedirs(restarts)
    _compliant(os.path.join(work_dir, 'output.nc'))
    _compliant(os.path.join(restarts, 'ocn.rst.0001-01-02_00.00.00.nc'))
    _noncompliant(os.path.join(restarts, 'ocn.rst.0001-01-01_00.00.00.nc'))
    with open(os.path.join(work_dir, 'omega.yml'), 'w') as f:
        f.write(OMEGA_YAML.format(restarts=restarts))
    step = _omega_step(work_dir, model='omega')
    assert step.check_cf() == (True, False)
    filenames = [r['filename'] for r in step.cf_check_results]
    assert filenames == [
        'restarts/ocn.rst.0001-01-01_00.00.00.nc',
        'output.nc',
    ]


def test_mpas_ocean_step_is_not_checked(work_dir):
    _noncompliant(os.path.join(work_dir, 'output.nc'))
    step = _omega_step(work_dir, model='mpas-ocean')
    assert step.check_cf() == (False, True)


def test_check_step_cf_leaves_a_marker(work_dir):
    _compliant(os.path.join(work_dir, 'good.nc'))
    _noncompliant(os.path.join(work_dir, 'bad.nc'))
    step = _step(work_dir)
    assert _check_step_cf(step, 'forward') is None
    assert _read_cf_status_from_logs(work_dir) is None

    step.add_cf_check('good.nc')
    assert _check_step_cf(step, 'forward') is True
    assert _read_cf_status_from_logs(work_dir) is True

    step.add_cf_check('bad.nc')
    assert _check_step_cf(step, 'forward') is False
    assert _read_cf_status_from_logs(work_dir) is False
    with open(os.path.join(work_dir, 'cf_check_failed.log')) as f:
        message = f.read()
    assert 'bad.nc' in message
    assert 'Invalid units' in message
    assert 'The following files passed:\n  good.nc' in message


def test_cf_check_message_lists_errors_then_passes():
    results = [
        dict(filename='good.nc', passed=True, errors=[]),
        dict(filename='bad.nc', passed=False, errors=['x: bad units']),
    ]
    message = _cf_check_message(results, passed=False, step_name='forward')
    assert message.index('bad.nc') < message.index('good.nc')
    assert '    x: bad units' in message
    message = _cf_check_message(results[:1], passed=True, step_name='forward')
    assert message.startswith('CF check passed for step forward')


def test_result_lines_report_cf_failures():
    assert _result_lines({'total': 2}) == ['- Result: All tests passed']
    lines = _result_lines({'total': 2, 'cf': ['ocean/task']})
    assert lines == [
        '- Result:',
        '  - CF compliance failures (1 of 2):',
        '    - `ocean/task`',
    ]
