"""
Running one step in a process of its own.

Polaris already has the right unit: `polaris serial` run inside a step's
work directory loads `step.pickle` and executes that one step, with config,
parallel system, resources, logging and completion markers all handled.  The
executor starts that as a subprocess with the step's placement in its
environment and waits for it.  The same mechanism serves an MPI step, whose
subprocess goes on to launch its model, and a Python step, whose subprocess
simply runs Python.

What the two do not share is how they are confined.  An MPI step's placement
reaches a launcher, which puts the work where it says.  A step that is not
launched does its work in this process, and nothing between here and there
acts on a placement -- so the executor sets the process's own affinity.  It
can only do that on the node it is running on, which is why the pool gives
such a step cores on the scheduler's node.

A step placed on the local node is bound whether or not it goes on to launch
something.  The affinity of a launcher's *client* process is not what
decides where its tasks run: the batch system assigns those.  That is the
reading this is built on and it has not been checked on a machine, so it is
the first thing to look at if a placed MPI step ever comes back reporting
fewer cores than it was promised.
"""

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from polaris.run.placement import placement_to_env
from polaris.run.pool import Reservation

# what a step's process is: `polaris serial` in the step's work directory,
# told that it is a subprocess so that it does not start another one
STEP_COMMAND = ['polaris', 'serial', '--step_is_subprocess']


@dataclass(frozen=True)
class StepOutcome:
    """
    How a step ended.

    Attributes
    ----------
    step_path : str
        Which step this is about.

    returncode : int
        What its process exited with.  Negative means it was killed by a
        signal rather than exiting on its own.

    seconds : float
        How long it ran.

    signal_name : str or None
        The signal that killed it, where one did.

    succeeded : bool
        Whether it finished on its own with nothing to report.

    terminated : bool
        Whether it was killed rather than failing.  This is worth telling
        apart: memory is not enforced, so a step that uses more than it
        declared exhausts the node and the operating system kills whichever
        process it chooses, which need not be the step at fault.
    """

    step_path: str
    returncode: int
    seconds: float
    signal_name: Optional[str]
    succeeded: bool
    terminated: bool


class RunningStep:
    """
    A step that has been started and has not finished.

    Attributes
    ----------
    step : polaris.Step
        The step being run.

    reservation : polaris.run.pool.Reservation
        What it was given, which is handed back when it ends.

    log_filename : str
        Where its output is going.
    """

    def __init__(self, step, reservation, process, log_filename, log_handle):
        self.step = step
        self.reservation = reservation
        self.log_filename = log_filename
        self._process = process
        self._log_handle = log_handle
        self._started = time.time()

    @property
    def pid(self) -> int:
        """The process id, which is what a log names it by."""
        return self._process.pid

    def wait(self) -> StepOutcome:
        """
        Wait for the step to end and say how it went.

        Returns
        -------
        outcome : polaris.run.executor.StepOutcome
            What happened
        """
        returncode = self._process.wait()
        self._log_handle.close()
        return _outcome(
            self.step.path, returncode, time.time() - self._started
        )

    def kill(self) -> None:
        """Stop the step, for a run that is being torn down."""
        if self._process.poll() is None:
            self._process.kill()


def start_step(
    step, reservation: Reservation, log_filename: str, local_node: str
) -> RunningStep:
    """
    Start one step in a process of its own.

    Parameters
    ----------
    step : polaris.Step
        The step to run, which must already be set up

    reservation : polaris.run.pool.Reservation
        What the pool gave it

    log_filename : str
        Where to send its output.  Steps run at the same time, so they
        cannot share a stream and be read afterwards.

    local_node : str
        The node the scheduler is on, which is the only one whose cores the
        executor can bind a process to

    Returns
    -------
    running : polaris.run.executor.RunningStep
        The started step
    """
    environ = dict(os.environ)
    environ.update(placement_to_env(reservation.placement))

    os.makedirs(os.path.dirname(log_filename) or '.', exist_ok=True)
    handle = open(log_filename, 'w')

    cores = _local_cores(reservation, local_node)
    process = subprocess.Popen(
        STEP_COMMAND,
        cwd=step.work_dir,
        env=environ,
        stdout=handle,
        stderr=subprocess.STDOUT,
        preexec_fn=None if cores is None else _bind_to(cores),
    )
    return RunningStep(step, reservation, process, log_filename, handle)


def _local_cores(
    reservation: Reservation, local_node: str
) -> Optional[List[int]]:
    """
    The cores to bind a step's own process to, or ``None`` not to bind it.

    Only a step whose whole placement is on this node is bound.  A step
    spread over several nodes does its work through a launcher, which puts
    it where the placement says, and confining the process that started it
    would describe none of that.
    """
    names = list(reservation.cores)
    if len(names) != 1:
        return None
    name = names[0]
    if name not in ('', local_node):
        return None
    cores = list(reservation.cores[name])
    return cores or None


def _bind_to(cores: List[int]):
    """Make a function that confines the new process to these cores."""

    def bind():
        try:
            os.sched_setaffinity(0, set(cores))
        except (AttributeError, OSError):
            # a platform without affinity, or cores the kernel will not
            # give us.  The step still runs; the scheduler's accounting
            # describes it and nothing enforces that, which is the same
            # footing memory is on.
            pass

    return bind


def _outcome(step_path: str, returncode: int, seconds: float) -> StepOutcome:
    """Read a process's exit status the way a scheduler needs it."""
    signal_name = None
    terminated = returncode < 0
    if terminated:
        try:
            signal_name = signal.Signals(-returncode).name
        except ValueError:
            signal_name = f'signal {-returncode}'
    return StepOutcome(
        step_path=step_path,
        returncode=returncode,
        seconds=round(seconds, 3),
        signal_name=signal_name,
        succeeded=returncode == 0,
        terminated=terminated,
    )


def describe_neighbors(pool, reservation: Reservation, steps: Dict) -> str:
    """
    Name the steps that shared a node with one that was killed, and what
    each of them declared.

    The victim is identifiable and the culprit is not, so this is the most
    that can honestly be said.  A report that blamed only the victim would
    send whoever reads it to the wrong step, while the list of neighbours
    and their declarations is what turns an inexplicable failure into a
    short investigation -- and, where one neighbour's declaration is
    obviously too small, into an obvious fix.

    Parameters
    ----------
    pool : polaris.run.pool.ResourcePool
        The pool, which knows who is on which node

    reservation : polaris.run.pool.Reservation
        What the killed step held

    steps : dict of polaris.Step
        The steps of the run, by path

    Returns
    -------
    report : str
        Lines naming each node the step was on and who else was there
    """
    lines = []
    for node_name in reservation.cores:
        others = [
            path
            for path in pool.resident(node_name)
            if path != reservation.step_path
        ]
        lines.append(f'  on node {node_name or "this node"}:')
        if not others:
            lines.append('    nothing else was running there')
            continue
        for path in others:
            other = steps.get(path)
            if other is None:
                lines.append(f'    {path}')
                continue
            if other.memory is None:
                declared = (
                    f'declared no memory, budgeted at '
                    f'{other.memory_budget} MiB'
                )
            else:
                declared = f'declared {other.memory} MiB'
            lines.append(f'    {path}: {other.cores} cores, {declared}')
    return '\n'.join(lines)
