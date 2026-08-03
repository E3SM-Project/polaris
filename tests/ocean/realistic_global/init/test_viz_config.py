import re
from importlib.resources import files

import pytest

from polaris.config import PolarisConfigParser
from polaris.tasks.ocean.realistic_global.mesh_configs import (
    add_realistic_global_mesh_config,
)

# section_name = '...' assignments in the viz step
_SECTION_ASSIGNMENT = re.compile(r"^\s*section_name = '([^']+)'", re.MULTILINE)


def _viz_source():
    return (
        files('polaris.tasks.ocean.realistic_global.init')
        .joinpath('viz.py')
        .read_text()
    )


def _init_config():
    config = PolarisConfigParser()
    config.add_from_package('polaris.remap', 'mapping.cfg')
    config.add_from_package(
        'polaris.tasks.ocean.realistic_global.init',
        'realistic_global_init.cfg',
    )
    add_realistic_global_mesh_config(config=config, mesh_name='icos240km')
    return config


def test_viz_step_reads_only_sections_that_exist():
    """
    Every config section the viz step names must exist in the packaged
    config.  A typo here is invisible until a plotting step runs deep in a
    workflow, where it fails the whole task.
    """
    sections = set(_SECTION_ASSIGNMENT.findall(_viz_source()))
    assert sections, 'no section_name assignments found in viz.py'

    config = _init_config()
    missing = sorted(s for s in sections if not config.has_section(s))
    assert not missing, f'viz.py reads missing config sections: {missing}'


@pytest.mark.parametrize('option', ['projection', 'central_longitude'])
def test_viz_section_has_the_map_options(option):
    """
    The options the global-map plots read, including the forcing plots.
    """
    config = _init_config()
    assert config.has_option('realistic_global_init_viz', option)
