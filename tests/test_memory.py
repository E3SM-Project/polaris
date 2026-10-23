"""
Tests for the memory a step's output and log report.

`polaris serial` runs every step in one process, so these numbers are what
shows a step holding on to memory that later steps then run without.
"""

import os

import numpy as np
import pytest

from polaris import Component, Step
from polaris.config import PolarisConfigParser
from polaris.run import complete_step_run
from polaris.run.memory import (
    format_bytes,
    read_process_memory,
    reset_peak_memory,
)
from polaris.run.serial import run_step_in_process

MIB = 1024**2


class _Writer(Step):
    """A step that leaves an output behind."""

    def run(self):
        with open('made.txt', 'w') as handle:
            handle.write('the step ran')


def _writer(tmp_path, name):
    """A real step, set up as far as running one needs."""
    step = _Writer(component=Component(name='ocean'), name=name, subdir=name)
    step.work_dir = str(tmp_path / name)
    step.base_work_dir = str(tmp_path)
    os.makedirs(step.work_dir, exist_ok=True)
    step.outputs = [os.path.join(step.work_dir, 'made.txt')]

    config = PolarisConfigParser()
    config.add_from_package('polaris', 'default.cfg')
    config.add_from_package('polaris.machines', 'default.cfg')
    config.filepath = os.path.join(step.work_dir, f'{name}.cfg')
    with open(config.filepath, 'w') as handle:
        config.write(handle)
    step.config = config
    return step


def test_bytes_are_formatted_in_binary_units():
    assert format_bytes(None) == 'unknown'
    assert format_bytes(512) == '512.0 B'
    assert format_bytes(1536) == '1.5 KiB'
    assert format_bytes(3 * 1024**3) == '3.0 GiB'
    assert format_bytes(2 * 1024**4) == '2.0 TiB'


def test_the_peak_is_at_least_what_is_held():
    memory = read_process_memory()

    assert memory.peak > 0
    if memory.resident is not None:
        assert memory.peak >= memory.resident


def test_a_reset_peak_is_the_peak_of_what_follows():
    """
    The peak is reset before each step so that it is that step's: memory
    freed before the reset must not show in it, and memory used after must.
    """
    freed = np.ones(256 * MIB // 8)
    del freed
    peak_before = read_process_memory().peak
    if not reset_peak_memory():
        pytest.skip('the peak cannot be reset on this system')

    after_reset = read_process_memory()
    assert after_reset.peak < peak_before - 128 * MIB

    used = np.ones(256 * MIB // 8)
    after_use = read_process_memory()
    del used
    assert after_use.peak > after_reset.peak + 128 * MIB


def test_a_step_reports_its_memory_and_the_pickles_it_loaded(tmp_path, capsys):
    """
    The memory line goes beside the runtime, and the size of each
    dependency's pickle goes in the log, since a dependency is loaded whole.
    """
    dependency = _writer(tmp_path, 'dependency')
    step = _writer(tmp_path, 'step')
    step.add_dependency(dependency)
    here = os.getcwd()
    try:
        os.chdir(dependency.work_dir)
        complete_step_run(dependency)
        os.chdir(step.work_dir)
        run_step_in_process(step)
    finally:
        os.chdir(here)

    output = capsys.readouterr().out
    pickle_filename = os.path.join(
        dependency.work_dir, 'step_after_run.pickle'
    )
    assert f'loaded dependency dependency from {pickle_filename}' in output
    assert 'memory:' in output
    assert 'held after' in output
