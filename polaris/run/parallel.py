"""
Running a suite's independent steps at the same time.

The loop is conventional and is meant to stay that way:

1. Mark ready any step whose requirements have all succeeded.
2. Among ready steps, in a stable order, start each that fits in what is
   free.
3. Wait for any running step to finish.
4. Release what it held, record the outcome, and repeat.

The stable order is setup order -- suite, then task, then step within a task
-- which is easy to explain and close to what a reader already expects.  A
step that does not fit right now is skipped over until it does.  Nothing
holds resources back for a large step that cannot fit, on the argument that
the largest steps are started early by the stable order; if starvation shows
up in practice, that is the point to add a rule, with evidence for it.

A step's width is decided once, from the whole allocation, exactly as
`polaris serial` decides it, and the loop waits until that much is free.
Handing a step whatever happened to be free would make an MPI step's
decomposition depend on scheduling timing, and its results with it.
"""

import argparse
import os
import socket
import sys
import time
from datetime import timedelta
from typing import Dict, List

import mpas_tools.io
from mpas_tools.logging import LoggingContext

from polaris.parallel import set_parallel_systems
from polaris.run import setup_config, unpickle_suite
from polaris.run.allocation import read_allocation
from polaris.run.confinement import PLACEMENT_MISMATCH_LOG
from polaris.run.events import EventStream
from polaris.run.executor import (
    RunningStep,
    StepOutcome,
    describe_neighbors,
    reap_one,
    start_step,
)
from polaris.run.graph import build_step_graph
from polaris.run.lifecycle import (
    read_baseline_status_from_logs,
    read_property_status_from_logs,
)
from polaris.run.pool import ResourcePool
from polaris.run.serial import (
    _update_steps_to_run,
    end_color,
    error_str,
    fail_str,
    start_time_color,
    success_str,
)


def run_tasks(suite_name, quiet=False):
    """
    Run a suite or task, with independent steps running at the same time

    A task's pickle holds one task where a suite's holds several, and
    nothing else about them differs, so both arrive here.

    Parameters
    ----------
    suite_name : str
        The name of the suite, or ``'task'`` for a task

    quiet : bool, optional
        Whether step names are left out of the output as the run progresses
    """
    suite = unpickle_suite(suite_name)
    task = next(iter(suite['tasks'].values()))
    component = task.component
    common_config = setup_config(task.base_work_dir, f'{component.name}.cfg')
    set_parallel_systems(suite['tasks'], common_config)

    mpas_tools.io.default_format = common_config.get('io', 'format')
    mpas_tools.io.default_engine = common_config.get('io', 'engine')

    work_dir = suite.get('work_dir', os.getcwd())
    with LoggingContext(suite_name) as logger:
        os.environ['PYTHONUNBUFFERED'] = '1'
        events = EventStream(
            os.path.join(work_dir, f'{suite_name}_events.jsonl')
        )
        try:
            failures = _run(
                suite, suite_name, component, logger, events, work_dir, quiet
            )
        finally:
            events.close()

    if failures:
        sys.exit(1)


def _run(suite, suite_name, component, logger, events, work_dir, quiet):
    """Set the run up, drive the loop, and report what happened."""
    steps = _select_steps(suite, logger)

    # the nodes are read before the steps are sized, because what they
    # report is what the sizes have to be taken from
    nodes = read_allocation(component, logger)
    available = _credit_memory(component.get_available_resources(), nodes)
    for step in steps.values():
        step.constrain_resources(available)

    pool = ResourcePool(nodes, local_node=_local_node(nodes))
    graph = build_step_graph(steps.values())

    impossible = {
        path: pool.why_impossible(node.step)
        for path, node in graph.nodes.items()
        if not node.satisfied
    }
    impossible = {
        path: reason for path, reason in impossible.items() if reason
    }
    if impossible:
        for reason in impossible.values():
            logger.error(reason)
        raise ValueError(
            f'{len(impossible)} step(s) cannot run in this allocation. '
            f'Nothing has been run.'
        )

    events.record(
        'run_started',
        suite=suite_name,
        steps=len(graph.nodes),
        nodes=[node.name for node in nodes],
        cores=sum(node.cores for node in nodes),
    )
    started = time.time()
    outcomes, mismatched = _loop(
        graph, pool, steps, logger, events, work_dir, quiet
    )
    elapsed = time.time() - started

    failures = _report(outcomes, mismatched, steps, logger, elapsed)
    events.record(
        'run_finished', elapsed=round(elapsed, 3), failures=len(failures)
    )
    return failures


def _credit_memory(available, nodes):
    """
    Size steps against the memory the nodes credit, not the configured
    figure.

    A step that declares no memory is budgeted at its proportional share of
    a node, and that is what makes memory accounting neutral: the memory
    inequality and the core inequality become the same inequality, so a run
    in which nothing declares memory packs exactly as it would with no
    memory accounting at all.

    That neutrality holds only while the figure the share is taken from is
    the figure the pool charges against.  Taking the share from the
    machine's configured memory while crediting each node with what it
    reports breaks it, and breaks it in the direction that refuses work.
    Measured on Chrysalis: the configured 253000 MiB is about 5% above what
    a node reports available, so a step wanting the whole allocation was
    budgeted 759000 MiB against the 730758 MiB its three nodes credited,
    and could never start.  Two steps of a fifteen-step run were rejected
    before anything ran.

    The smallest node's figure is the one used, since a single number has
    to serve every node the step might land on and the smallest is the one
    that always fits.

    Parameters
    ----------
    available : dict
        The resource view from the parallel system

    nodes : list of polaris.run.allocation.NodeResources
        What the allocation's nodes reported

    Returns
    -------
    available : dict
        The same view, with memory taken from what the nodes credit
    """
    credited = [node.memory for node in nodes if node.memory is not None]
    if not credited:
        return available
    available = dict(available)
    available['memory_per_node'] = min(credited)
    available['memory'] = sum(credited)
    return available


def _select_steps(suite, logger) -> Dict:
    """
    The steps to run, in setup order, with a step shared between tasks once.

    Which steps a task runs comes from its config exactly as it does on the
    serial path, so that the two paths are asked to run the same work.
    """
    steps: Dict[str, object] = {}
    for task in suite['tasks'].values():
        config = setup_config(task.base_work_dir, task.config.filepath)
        task.config = config
        names = _update_steps_to_run(task.name, None, None, config, task.steps)
        for name in names:
            step = task.steps[name]
            if step.path not in steps:
                step.config = setup_config(
                    step.base_work_dir, step.config.filepath
                )
                steps[step.path] = step
    logger.info(f'Running {len(steps)} step(s)')
    return steps


def _local_node(nodes) -> str:
    """
    Which of the allocation's nodes this process is on.

    A batch script runs on one of its job's own nodes, so the hostname
    should match one of them.  Where it does not -- an interactive shell on
    a login node, say -- the first node is assumed, which is where a batch
    script would have been.
    """
    hostname = socket.gethostname().split('.')[0]
    for node in nodes:
        if node.name.split('.')[0] == hostname:
            return node.name
    return nodes[0].name if nodes else ''


def _loop(graph, pool, steps, logger, events, work_dir, quiet):
    """Start what fits, wait for what finishes, and keep going."""
    succeeded = {path for path, node in graph.nodes.items() if node.satisfied}
    for path in succeeded:
        events.record('step_skipped', step=path, reason='already satisfied')
        if not quiet:
            logger.info(f'  * {path}: already done')

    outcomes: Dict[str, StepOutcome] = {}
    mismatched: List[str] = []
    blocked: Dict[str, str] = {}
    running: Dict[str, RunningStep] = {}
    waiting = set(graph.nodes) - succeeded

    try:
        while waiting or running:
            started_any = _start_what_fits(
                graph,
                pool,
                waiting,
                running,
                succeeded,
                blocked,
                logger,
                events,
                work_dir,
                quiet,
            )
            if not running:
                if started_any:
                    continue
                # nothing is running and nothing could start, so nothing ever
                # will.  This is a bug in the scheduler rather than in the run,
                # and saying which steps are stuck is what makes it findable.
                events.record('run_stalled', waiting=sorted(waiting))
                raise RuntimeError(
                    f'Nothing is running and none of the {len(waiting)} '
                    f'remaining step(s) can start: {sorted(waiting)}'
                )

            # reaped here rather than by a thread per running step:
            # only the forking thread survives a fork, so a lock held
            # by any other one then is held forever in the child
            outcome = reap_one(running)
            step_run = running.pop(outcome.step_path)
            _finish(
                outcome,
                step_run,
                graph,
                pool,
                steps,
                succeeded,
                waiting,
                outcomes,
                mismatched,
                logger,
                events,
                quiet,
            )
    finally:
        # nothing may outlive the scheduler.  A forked child is a
        # direct child of this process, so an interrupt that left one
        # running would leave a model holding cores with nothing
        # watching it, and a child never reaped is a zombie for as
        # long as the scheduler lives.
        _abandon(running, logger, events)

    return outcomes, mismatched


def _abandon(running, logger, events) -> None:
    """
    Stop and reap whatever is still running, on the way out.

    Reached when the loop ends early -- an interrupt, or a bug in the
    scheduler -- and does nothing in the ordinary case, where every step has
    already been reaped.
    """
    for path, step_run in sorted(running.items()):
        logger.warning(f'  * {path}: stopping, the run is being torn down')
        events.record('step_abandoned', step=path, pid=step_run.pid)
        step_run.kill()
    for _ in running:
        try:
            os.waitpid(-1, 0)
        except ChildProcessError:
            break
    running.clear()


def _start_what_fits(
    graph,
    pool,
    waiting,
    running,
    succeeded,
    blocked,
    logger,
    events,
    work_dir,
    quiet,
):
    """Start every ready step that fits, in the order setup listed them."""
    started_any = False
    for path, node in graph.nodes.items():
        if path not in waiting:
            continue
        if not node.requires <= succeeded:
            continue
        reservation = pool.reserve(node.step)
        if reservation is None:
            if blocked.get(path) != 'resources':
                blocked[path] = 'resources'
                events.record('step_blocked', step=path, reason='resources')
            continue
        blocked.pop(path, None)
        waiting.discard(path)
        log_filename = _log_filename(work_dir, path)
        step_run = start_step(
            node.step, reservation, log_filename, pool.local_node
        )
        running[path] = step_run
        started_any = True
        events.record(
            'step_started',
            step=path,
            pid=step_run.pid,
            nodes=list(reservation.cores),
            cores=sum(len(cores) for cores in reservation.cores.values()),
            gpus=reservation.placement.gpus,
            memory=sum(reservation.memory.values()),
            log=log_filename,
        )
        if not quiet:
            logger.info(f'  * {path}: started on {list(reservation.cores)}')
    return started_any


def _finish(
    outcome,
    step_run,
    graph,
    pool,
    steps,
    succeeded,
    waiting,
    outcomes,
    mismatched,
    logger,
    events,
    quiet,
):
    """Take back what a step held and act on how it ended."""
    outcomes[outcome.step_path] = outcome
    if _placement_mismatch(steps.get(outcome.step_path), logger):
        mismatched.append(outcome.step_path)
        events.record('placement_mismatch', step=outcome.step_path)
    neighbors = ''
    if outcome.terminated:
        # asked before the reservation goes back, since afterwards the step
        # is no longer resident anywhere
        neighbors = describe_neighbors(pool, step_run.reservation, steps)
    pool.release(step_run.reservation)

    if outcome.succeeded:
        succeeded.add(outcome.step_path)
        events.record(
            'step_finished',
            step=outcome.step_path,
            status='succeeded',
            duration=outcome.seconds,
        )
        if not quiet:
            logger.info(
                f'  * {outcome.step_path}: {success_str} '
                f'{start_time_color}{outcome.seconds:.1f}s{end_color}'
            )
        return

    status = 'terminated' if outcome.terminated else 'failed'
    events.record(
        'step_finished',
        step=outcome.step_path,
        status=status,
        duration=outcome.seconds,
        returncode=outcome.returncode,
        signal=outcome.signal_name,
    )
    if outcome.terminated:
        logger.error(
            f'  * {outcome.step_path}: {error_str} killed by '
            f'{outcome.signal_name}. Nothing enforces memory, so a step that '
            f'used more than it declared can exhaust a node and the '
            f'operating system kills whichever process it chooses -- which '
            f'need not be the step at fault. These were on its node(s):\n'
            f'{neighbors}'
        )
    else:
        logger.error(
            f'  * {outcome.step_path}: {fail_str} '
            f'(exit code {outcome.returncode}), see {step_run.log_filename}'
        )

    blocked = graph.descendants(outcome.step_path) & waiting
    for path in sorted(blocked):
        waiting.discard(path)
        events.record(
            'step_skipped', step=path, reason=f'{outcome.step_path} failed'
        )
    if blocked:
        logger.error(
            f'      {len(blocked)} step(s) that needed it will not run'
        )


def _log_filename(work_dir: str, path: str) -> str:
    """
    Where one step's output goes.

    A step's output cannot go where the serial path puts it: steps of a task
    no longer run one after another, so a log per task would interleave
    several steps and could not be attributed afterwards.  One file per
    step, named for its path, in the directory the serial path already
    keeps its logs in.
    """
    return os.path.join(
        work_dir, 'case_outputs', f'{path.replace("/", "_")}.log'
    )


def _placement_mismatch(step, logger) -> bool:
    """
    Say whether a step reported that it did not get what it was placed on.

    The step writes this beside its own log because it is the only thing in
    a position to look, and the scheduler reads it because a warning in one
    of fifteen concurrent logs is a warning nobody sees.
    """
    if step is None:
        return False
    filename = os.path.join(step.work_dir, PLACEMENT_MISMATCH_LOG)
    if not os.path.exists(filename):
        return False
    with open(filename) as handle:
        logger.warning('')
        logger.warning(handle.read().rstrip())
    return True


def _comparisons(steps, logger) -> List[str]:
    """
    Say what the steps' own comparisons decided, and give back what differed.

    Each step compares itself against the baseline in its own process and
    leaves the verdict beside its log, exactly as the serial path does.  What
    the serial path also does, and this did not, is add them up: a run of a
    hundred steps against a baseline is asking one question -- did anything
    change -- and the answer must not be something you have to go and find.
    """
    outcome: Dict[str, List[List[str]]] = {
        'baseline': [[], []],
        'property': [[], []],
    }
    readers = {
        'baseline': read_baseline_status_from_logs,
        'property': read_property_status_from_logs,
    }
    for path in sorted(steps):
        for kind, reader in readers.items():
            status = reader(steps[path].work_dir)
            if status is not None:
                outcome[kind][0 if status else 1].append(path)

    for kind, label in (
        ('baseline', 'Baseline comparison'),
        ('property', 'Property checks'),
    ):
        passed, failed = outcome[kind]
        if not passed and not failed:
            continue
        logger.info('')
        logger.info(f'{label}: {len(passed)} passed, {len(failed)} failed')
        for path in failed:
            logger.error(f'  {fail_str} {path}')

    # only a baseline difference fails the run, because that is what the
    # serial path does with one.  A failed property check does not fail
    # anything there -- `property_passed` is accumulated in serial.py and
    # never read -- and four steps of omega_pr fail one today.  Failing here
    # on something serial ignores would make a suite that passes one step at
    # a time fail when run concurrently, for a reason that has nothing to do
    # with concurrency, and Phase B would be blamed for it.  Whether a failed
    # property check ought to fail a task is a real question and is being
    # settled on its own branch; this follows serial either way.
    return list(outcome['baseline'][1])


def _report(outcomes, mismatched, steps, logger, elapsed) -> List[str]:
    """Say how it went, and how that compares with running one at a time."""
    failures = [
        path for path, outcome in outcomes.items() if not outcome.succeeded
    ]
    # the steps' own work, not the time from forking each to reaping it.
    # Counting startup as work is how an earlier implementation reported
    # omega_pr as doing 7.2x the work of a serial run on a run that was
    # slower than serial: 4,200 s of Python imports counted as work, and a
    # figure that says the run is healthy while the wall clock says
    # otherwise is worse than no figure.
    step_seconds = sum(
        outcome.work_seconds
        if outcome.work_seconds is not None
        else outcome.seconds
        for outcome in outcomes.values()
    )

    logger.info('')
    logger.info('Step runtimes:')
    for path, outcome in outcomes.items():
        status = success_str if outcome.succeeded else fail_str
        logger.info(f'  {outcome.seconds:8.1f}s {status} {path}')

    elapsed_str = str(timedelta(seconds=round(elapsed)))
    logger.info(f'Total runtime: {elapsed_str}')
    if elapsed > 0:
        logger.info(
            f'Step time was {step_seconds:.0f}s, so this run did '
            f'{step_seconds / elapsed:.1f}x the work of running one step at '
            f'a time for as long.'
        )

    differed = _comparisons(steps, logger)
    for path in differed:
        if path not in failures:
            failures.append(path)

    if mismatched:
        logger.warning('')
        logger.warning(
            f'{len(mismatched)} step(s) did not get the part of the '
            f'allocation they were placed on, so the packing above does not '
            f'describe how this run used the machine: '
            f'{", ".join(mismatched)}'
        )

    if failures:
        logger.error(
            f'FAIL: {len(failures)} step(s) failed or differed from '
            f'the baseline, see above.'
        )
    else:
        logger.info('PASS: All passed successfully!')
    return failures


def main():
    parser = argparse.ArgumentParser(
        description='Run a suite or task with steps running at the same time',
        prog='polaris parallel',
    )
    parser.add_argument(
        'suite',
        nargs='?',
        help='The name of a suite to run. Can exclude or include the '
        '.pickle filename suffix.',
    )
    parser.add_argument(
        '-q',
        '--quiet',
        dest='quiet',
        action='store_true',
        help='If set, step names are not included in the output as the run '
        'progresses.',
    )
    args = parser.parse_args(sys.argv[2:])

    if args.suite is not None:
        run_tasks(args.suite, quiet=args.quiet)
    elif os.path.exists('task.pickle'):
        run_tasks('task', quiet=args.quiet)
    else:
        raise OSError(
            'No suite was given and no task.pickle was found here. Are you '
            'sure this is a polaris suite or task work directory?'
        )
