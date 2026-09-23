"""
Tests for the convergence-rate check in ``ConvergenceAnalysis``.

When a baseline was given, the rate fitted to the baseline's errors used to
replace the run's own rate before the threshold check, so a run passed or
failed on the baseline's convergence rather than its own.
"""

import logging
from functools import partial

import pandas as pd
import pytest

from polaris.config import PolarisConfigParser
from polaris.ocean.convergence.analysis import ConvergenceAnalysis
from polaris.tasks.ocean import Ocean

RESOLUTIONS = [120.0, 60.0, 30.0]
CONV_THRESH = 1.9


def _make_config():
    config = PolarisConfigParser()
    config.add_section('convergence')
    config.set('convergence', 'base_resolution', '30.0')
    config.set('convergence', 'refinement_factors_space', '4.0, 2.0, 1.0')
    config.set('convergence', 'convergence_thresh', str(CONV_THRESH))
    config.set('convergence', 'error_type', 'l2')
    config.add_section('convergence_forward')
    config.set('convergence_forward', 'time_integrator', 'RK4')
    config.set('convergence_forward', 'rk4_dt_per_km', '3.0')
    return config


def _power_law_error(order, refinement_factor, **kwargs):
    return (refinement_factor * 30.0) ** order


def _make_step(tmp_path, monkeypatch, order, baseline_order):
    step = ConvergenceAnalysis(
        component=Ocean(),
        subdir='analysis',
        dependencies={},
        convergence_vars=[],
        refinement='space',
    )
    step.config = _make_config()
    step.logger = logging.getLogger('test_convergence_analysis')
    step.work_dir = str(tmp_path / 'work')
    (tmp_path / 'work').mkdir()

    baseline_dir = tmp_path / 'baseline'
    baseline_dir.mkdir()
    pd.DataFrame(
        {
            'resolution': RESOLUTIONS,
            'l2': [res**baseline_order for res in RESOLUTIONS],
        }
    ).to_csv(baseline_dir / 'convergence_tracer1.csv', index=False)
    step.baseline_dir = str(baseline_dir)
    monkeypatch.setattr(
        step, 'compute_error', partial(_power_law_error, order)
    )
    return step


@pytest.mark.parametrize(
    'order, baseline_order, expected_failure',
    [(2.0, 1.0, False), (1.0, 2.0, True)],
)
def test_rate_is_checked_against_the_run_not_the_baseline(
    tmp_path, monkeypatch, order, baseline_order, expected_failure
):
    step = _make_step(tmp_path, monkeypatch, order, baseline_order)
    failed = step.plot_convergence('tracer1', 'tracer1', zidx=None)
    assert failed == expected_failure
