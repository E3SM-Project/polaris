"""
Unit tests for the mapping from a field name to its config section.

The mapping exists because field names are the models' own, and therefore
camel case, while Polaris config sections are lower case with underscores.
What matters is that the conversion is right and that the sections it names
are the ones ``analysis.cfg`` actually ships, so a field whose section was
spelled by hand does not go unnoticed until someone plots it.
"""

import pytest

from polaris.config import PolarisConfigParser
from polaris.tasks.ocean.analysis.climatology_maps import FIELD_GROUPS
from polaris.tasks.ocean.analysis.config_sections import (
    camel_to_snake,
    map_section,
)


@pytest.mark.parametrize(
    'name, expected',
    [
        ('ssh', 'ssh'),
        ('temperature', 'temperature'),
        ('velocityZonal', 'velocity_zonal'),
        ('velocityMeridional', 'velocity_meridional'),
        ('mixedLayerDepth', 'mixed_layer_depth'),
        ('heatContent', 'heat_content'),
        ('PseudoThickness', 'pseudo_thickness'),
        ('zMid', 'z_mid'),
        ('maxLevelCell', 'max_level_cell'),
    ],
)
def test_camel_case_becomes_lower_case_with_underscores(name, expected):
    assert camel_to_snake(name) == expected


def test_a_name_that_is_already_snake_case_is_unchanged():
    for name in ('mixed_layer_depth', 'heat_content', 'ssh'):
        assert camel_to_snake(name) == name


def test_the_section_is_the_prefix_and_the_converted_field():
    assert map_section('velocityZonal') == 'ocean_analysis_map_velocity_zonal'
    assert map_section('ssh') == 'ocean_analysis_map_ssh'


def test_every_mappable_field_has_a_section_in_analysis_cfg():
    config = PolarisConfigParser()
    config.add_from_package('polaris.tasks.ocean.analysis', 'analysis.cfg')
    fields = [field for fields in FIELD_GROUPS.values() for field in fields]
    assert fields
    for field in fields:
        section = map_section(field)
        assert config.has_section(section), (
            f'analysis.cfg has no [{section}] for the field {field}'
        )
