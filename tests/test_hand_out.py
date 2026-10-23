"""
Tests for a step that hands out pieces of its work, run the way the
scheduler runs it.

The step is forked by the executor and goes through the same lifecycle as
any other, so its log, its outputs and its completion marker are checked as
well as its pieces.  A resident forked from the test process stands in for
the resident on the step's node.
"""

import logging
import os

import pytest

from polaris import Component, Step
from polaris.config import PolarisConfigParser
from polaris.run import STEP_COMPLETE_LOG
from polaris.run.allocation import NodeResources
from polaris.run.confinement import PLACEMENT_MISMATCH_LOG, check_confinement
from polaris.run.executor import reap_one, start_step
from polaris.run.pool import ResourcePool
from polaris.run.residents import Residents

PREAMBLE = 'Running step:'
FOOTER = 'execution:'


def square(value):
    return value * value


class _Squares(Step):
    """A step that hands out its work and writes down what came back."""

    def run_pieces(self, pieces):
        squares = pieces.map(square, range(5))
        with open(self.work_path('squares.txt'), 'w') as handle:
            handle.write(','.join(str(each) for each in squares))
        with open(self.work_path('own_cores.txt'), 'w') as handle:
            handle.write(str(len(os.sched_getaffinity(0))))


@pytest.fixture
def residents():
    with Residents() as started:
        started.start_local(['node0'])
        started.wait_until_ready(timeout=60)
        yield started


def _squares(tmp_path, cores=2):
    name = 'squares'
    step = _Squares(
        component=Component(name='ocean'), name=name, subdir=name, cores=cores
    )
    step.work_dir = str(tmp_path / name)
    step.base_work_dir = str(tmp_path)
    os.makedirs(step.work_dir, exist_ok=True)
    step.outputs = [os.path.join(step.work_dir, 'squares.txt')]

    config = PolarisConfigParser()
    config.add_from_package('polaris', 'default.cfg')
    config.add_from_package('polaris.machines', 'default.cfg')
    config.filepath = os.path.join(step.work_dir, f'{name}.cfg')
    with open(config.filepath, 'w') as handle:
        config.write(handle)
    step.config = config
    return step


def _reserve(step):
    """A reservation on this machine's own cores, named as the resident."""
    allowed = tuple(sorted(os.sched_getaffinity(0)))
    nodes = [
        NodeResources(
            name='node0',
            cores=len(allowed),
            core_ids=allowed,
            gpus=0,
            memory=None,
            memory_source='available',
            memory_total=None,
            memory_configured=None,
        )
    ]
    step.memory_budget = None
    reservation = ResourcePool(nodes, local_node='node0').reserve(step)
    assert reservation is not None
    return reservation


def _run(step, tmp_path, residents=None):
    log_filename = str(tmp_path / 'squares.log')
    running = start_step(
        step, _reserve(step), log_filename, 'node0', residents=residents
    )
    outcome = reap_one({step.path: running})
    with open(log_filename) as handle:
        return outcome, handle.read()


def test_a_step_hands_out_its_work_through_the_residents(tmp_path, residents):
    step = _squares(tmp_path)
    outcome, log = _run(step, tmp_path, residents.directory)
    assert outcome.succeeded, log
    with open(os.path.join(step.work_dir, 'squares.txt')) as handle:
        assert handle.read() == '0,1,4,9,16'
    assert PREAMBLE in log and FOOTER in log
    assert 'handing out 5 piece(s) of square over 2 core(s)' in log
    assert os.path.exists(os.path.join(step.work_dir, STEP_COMPLETE_LOG))


def test_its_own_process_is_not_bound_to_its_cores(tmp_path, residents):
    if len(os.sched_getaffinity(0)) < 3:
        pytest.skip('needs more cores than the step takes')
    step = _squares(tmp_path)
    outcome, log = _run(step, tmp_path, residents.directory)
    assert outcome.succeeded, log
    with open(os.path.join(step.work_dir, 'own_cores.txt')) as handle:
        assert int(handle.read()) == len(os.sched_getaffinity(0))


def test_a_step_that_hands_out_work_without_residents_says_so(tmp_path):
    step = _squares(tmp_path)
    outcome, log = _run(step, tmp_path, residents=None)
    assert not outcome.succeeded
    assert 'no residents were started' in log


def test_its_own_process_is_not_held_to_its_cores(tmp_path):
    step = _squares(tmp_path)
    step.placement = _reserve(step).placement
    check_confinement(step, logging.getLogger('test'))
    mismatch = os.path.join(step.work_dir, PLACEMENT_MISMATCH_LOG)
    assert not os.path.exists(mismatch)
