"""
Guard against the options Omega removed creeping back into task yaml files.

Omega replaced ``StopTime`` and ``RunDuration`` with a ``StopType`` naming the
kind of stop criterion in use and a ``StopCriterion`` holding its value.  A
task that writes the old names into an ``Omega:`` block bypasses the
MPAS-Ocean-to-Omega option map entirely, so
:py:meth:`polaris.ocean.model.OceanModelStep._map_stop_options` cannot
translate them, and setup fails only once that particular task is set up
against a current Omega.  This test finds them without running anything.
"""

from pathlib import Path

import pytest
from ruamel.yaml import YAML

#: Options Omega no longer has
REMOVED_OPTIONS = ['StopTime', 'RunDuration']

#: The repository's task and framework yaml files
POLARIS_ROOT = Path(__file__).resolve().parents[2] / 'polaris'


def _yaml_files():
    """Every yaml file shipped with polaris, excluding caches"""
    return sorted(
        p for p in POLARIS_ROOT.rglob('*.yaml') if '__pycache__' not in p.parts
    )


def _omega_time_integration(path):
    """
    The ``Omega: TimeIntegration:`` mapping in ``path``, or ``None``.

    Files that are Jinja templates rather than plain yaml are skipped: they
    cannot be parsed before rendering, and the ones that exist are covered by
    the rendered-config checks in the tasks themselves.
    """
    try:
        parsed = YAML(typ='safe').load(path.read_text())
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    omega = parsed.get('Omega')
    if not isinstance(omega, dict):
        return None
    section = omega.get('TimeIntegration')
    return section if isinstance(section, dict) else None


@pytest.mark.parametrize('path', _yaml_files(), ids=lambda p: p.name)
def test_no_removed_omega_stop_options(path):
    section = _omega_time_integration(path)
    if section is None:
        return

    found = [option for option in REMOVED_OPTIONS if option in section]

    assert not found, (
        f'{path.relative_to(POLARIS_ROOT.parent)} sets {", ".join(found)} '
        f'under Omega: TimeIntegration:, which Omega no longer has.  Use '
        f'StopType with StopCriterion instead, or set config_run_duration / '
        f'config_stop_time in the shared ocean section and let the option '
        f'map translate them.'
    )
