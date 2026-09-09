"""
Tests for how conservation property checks are declared and reported.

A property check that fails used to be written to a log file and then
discarded, so a task with a failing budget still reported PASS.  These tests
cover the pieces that make the check count: the tolerance overrides carried
on each check, and the suite summary that lists the tasks whose checks
failed.
"""

import pytest

from polaris import Component, Step
from polaris.run.serial import _result_summary_lines


def _make_step():
    return Step(component=Component(name='ocean'), name='step')


def test_property_check_records_its_arguments():
    step = _make_step()
    step.add_property_check(
        'output.nc', ['mass conservation'], baseline=-2, time_index_end=-1
    )
    assert len(step.properties_to_check) == 1
    check = step.properties_to_check[0]
    assert check['filename'] == 'output.nc'
    assert check['properties'] == ['mass conservation']
    assert check['baseline'] == -2
    assert check['time_index_end'] == -1
    assert check['tolerances'] == {}


def test_add_output_file_forwards_tolerances():
    step = _make_step()
    step.add_output_file(
        'output.nc',
        check_properties=['salt conservation'],
        check_properties_tolerances={'salt conservation': 1e-12},
    )
    assert step.properties_to_check[0]['tolerances'] == {'salt': 1e-12}


@pytest.mark.parametrize('name', ['salt', 'salt conservation'])
def test_tolerance_keys_accept_either_spelling(name):
    step = _make_step()
    step.add_property_check(
        'output.nc', ['salt conservation'], tolerances={name: 1e-12}
    )
    assert step.properties_to_check[0]['tolerances'] == {'salt': 1e-12}


@pytest.mark.parametrize('tolerance', [0.0, -1e-12])
def test_a_nonpositive_tolerance_is_rejected(tolerance):
    step = _make_step()
    with pytest.raises(ValueError, match='must be positive'):
        step.add_property_check(
            'output.nc',
            ['salt conservation'],
            tolerances={'salt': tolerance},
        )


def test_an_unexpected_baseline_is_rejected():
    step = _make_step()
    with pytest.raises(ValueError, match='Unexpected conservation baseline'):
        step.add_property_check(
            'output.nc', ['mass conservation'], baseline='final'
        )


def test_summary_reports_all_tests_passed():
    results = dict(total=3, failures=[], diffs=[], properties=[])
    assert _result_summary_lines(results) == ['- Result: All tests passed']


def test_summary_lists_property_check_failures():
    results = dict(
        total=3, failures=[], diffs=[], properties=['ocean/column/ekman']
    )
    lines = _result_summary_lines(results)
    assert lines == [
        '- Result:',
        '  - Property checks (1 of 3):',
        '    - `ocean/column/ekman`',
    ]


def test_a_property_failure_alone_is_not_all_tests_passed():
    # the whole point of the plumbing: a failing budget has to show up even
    # when nothing crashed and nothing differs from the baseline
    results = dict(
        total=2, failures=[], diffs=[], properties=['ocean/column/ekman']
    )
    assert _result_summary_lines(results)[0] == '- Result:'
