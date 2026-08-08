import re
from importlib.resources import files

import pytest

from polaris.config import PolarisConfigParser
from polaris.tasks.ocean.realistic_global.mesh_configs import (
    add_realistic_global_mesh_config,
)
from polaris.viz.helper import get_viz_defaults

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


def test_no_colormap_is_chosen_by_a_literal():
    """
    Colormaps belong in the shared viz defaults, not in plotting code, so
    that one variable gets one colormap everywhere it is plotted.

    Comparisons against a colormap name are fine -- ``_set_colormap`` has to
    recognise a diverging map to centre its range on zero -- so only lines
    that name a colormap without testing it count as a choice.
    """
    chosen = [
        line.strip()
        for line in _viz_source().splitlines()
        if re.search(r"'(cmo\.[a-z]+|viridis|plasma|magma)'", line)
        and '==' not in line
    ]
    assert not chosen, f'viz.py hard-codes a colormap choice: {chosen}'


@pytest.mark.parametrize(
    'var_name, colormap',
    [
        ('windStressZonal', 'cmo.balance'),
        ('windStressMeridional', 'cmo.balance'),
        # a magnitude is non-negative, so a diverging map would waste half
        # the colorbar
        ('windStressMagnitude', 'cmo.speed'),
    ],
)
def test_wind_stress_colormaps_come_from_the_viz_defaults(var_name, colormap):
    """
    The forcing plots look these up by the name they save the figure under,
    so the viz defaults have to carry an entry for each one; otherwise they
    silently fall back to 'default'.
    """
    viz_dict = get_viz_defaults()
    assert var_name in viz_dict
    assert viz_dict[var_name]['colormap'] == colormap
