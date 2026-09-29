"""
Unit tests for which variables the climatology is computed for.

Velocity components the simulation did not write are reconstructed from the
climatology of the edge-normal velocity, so that is what the climatology
has to carry for them, and only when the components themselves are missing.
"""

from polaris.config import PolarisConfigParser
from polaris.tasks.ocean.analysis.climatology import (
    _drop_unneeded_for_reconstruction,
    get_climatology_variables,
)

SUFFIX = '_TimeMean1Month'

PAIRS = [
    ('temperature', 'Temperature'),
    ('velocityZonal', 'velocityZonal'),
    ('velocityMeridional', 'velocityMeridional'),
    ('normalVelocity', 'NormalVelocity'),
]


def test_normal_velocity_is_added_for_the_velocity_components():
    config = _config('temperature, velocityZonal')
    variables = get_climatology_variables(config)
    assert 'normalVelocity' in variables


def test_normal_velocity_is_not_added_without_them():
    variables = get_climatology_variables(_config('temperature, ssh'))
    assert 'normalVelocity' not in variables


def test_components_that_can_be_reconstructed_are_not_missing():
    pairs = _drop_unneeded_for_reconstruction(
        PAIRS, _written('Temperature', 'NormalVelocity'), SUFFIX
    )
    assert [polaris for polaris, _ in pairs] == [
        'temperature',
        'normalVelocity',
    ]


def test_normal_velocity_is_not_needed_if_the_components_were_written():
    pairs = _drop_unneeded_for_reconstruction(
        PAIRS,
        _written(
            'Temperature',
            'velocityZonal',
            'velocityMeridional',
            'NormalVelocity',
        ),
        SUFFIX,
    )
    assert 'normalVelocity' not in [polaris for polaris, _ in pairs]


def test_nothing_is_dropped_if_nothing_can_be_reconstructed():
    """The components are then reported missing, as any field is."""
    pairs = _drop_unneeded_for_reconstruction(
        PAIRS, _written('Temperature'), SUFFIX
    )
    assert pairs == PAIRS


def _config(fields):
    config = PolarisConfigParser()
    config.add_from_package('polaris.tasks.ocean.analysis', 'analysis.cfg')
    config.set('ocean_analysis_climatology', 'fields', fields, user=True)
    return config


def _written(*names):
    return {f'{name}{SUFFIX}' for name in names}
