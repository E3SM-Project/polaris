"""
Running one step in a forked child.

The scheduler forks itself for each step it starts.  The child is a private
copy of the scheduler's address space, so it already holds every module the
scheduler imported and the live `Step` object the scheduler selected: it
imports nothing and unpickles nothing, which is what makes starting a step
cost almost nothing.  Starting each step as a fresh `polaris serial`
subprocess cost 35 s of imports and unpickling, more than the median step's
own work, and made a concurrent `omega_pr` slower than a serial one.

Being a copy is also what keeps the steps apart.  A step may change the
working directory, set library defaults and use `pyplot` globals exactly as
it does today, because none of it is shared.

The same mechanism serves an MPI step, whose child goes on to launch its
model, and a Python step, whose child simply runs Python.  What the two do
not share is how they are confined.  An MPI step's placement reaches a
launcher, which puts the work where it says.  A step that is not launched
does its work in the child itself, and nothing between the scheduler and
that child acts on a placement -- so the child sets its own affinity, which
it can only do on the node it is running on.  That is why the pool gives
such a step cores on the scheduler's node.

Forking safely requires the scheduler to hold no other thread; see
`polaris/__init__.py`, which pins the numerical thread pools before numpy
can raise one per core, and `reap_one` below, which is why the scheduler
does not give each running step a thread to wait on it.
"""

import os
import signal
import sys
import time
import traceback
from dataclasses import dataclass
from typing import Dict, List, NoReturn, Optional

from polaris.run.pool import Reservation
from polaris.run.serial import run_step_in_process


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
        How long its process took, from forking it to reaping it.

    work_seconds : float or None
        How long the step itself took, which is what a run should count as
        work.  ``None`` where the child could not say, which is any failure
        before it started timing.

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
    work_seconds: Optional[float] = None


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

    def __init__(self, step, reservation, pid, log_filename, started, hearing):
        self.step = step
        self.reservation = reservation
        self.log_filename = log_filename
        self.started = started
        self._pid = pid
        self._hearing = hearing

    def work_seconds(self) -> Optional[float]:
        """How long the step itself took, as the child reported it."""
        try:
            said = os.read(self._hearing, 64)
            os.close(self._hearing)
        except OSError:
            return None
        try:
            return float(said)
        except ValueError:
            # a child that died before it timed anything says nothing
            return None

    @property
    def pid(self) -> int:
        """The process id, which is what a log names it by."""
        return self._pid

    def kill(self) -> None:
        """Stop the step, for a run that is being torn down."""
        try:
            os.kill(self._pid, signal.SIGKILL)
        except ProcessLookupError:
            # it finished between deciding to kill it and doing so
            pass


def start_step(
    step, reservation: Reservation, log_filename: str, local_node: str
) -> RunningStep:
    """
    Start one step in a forked child.

    The child inherits this process's address space, so it holds every module
    already imported and the live ``step`` object, and reads nothing from
    disk to get going.  That is what makes starting a step cost almost
    nothing; a fresh ``polaris serial`` subprocess cost 35 s of imports and
    unpickling, which was more than the median step's actual work.

    Parameters
    ----------
    step : polaris.Step
        The step to run, which must already be set up and sized

    reservation : polaris.run.pool.Reservation
        What the pool gave it

    log_filename : str
        Where to send its output.  Steps run at the same time, so they
        cannot share a stream and be read afterwards.

    local_node : str
        The node the scheduler is on, which is the only one whose cores a
        child can bind itself to

    Returns
    -------
    running : polaris.run.executor.RunningStep
        The started step
    """
    os.makedirs(os.path.dirname(log_filename) or '.', exist_ok=True)
    cores = _local_cores(reservation, local_node)

    # anything still buffered here would be inherited and written twice
    sys.stdout.flush()
    sys.stderr.flush()

    # how the child says how long the step itself took.  A pipe rather than
    # another marker file: this is the scheduler's business rather than the
    # step's, and it should leave nothing behind in the work directory.
    hearing, saying = os.pipe()

    started = time.time()
    pid = os.fork()
    if pid == 0:
        os.close(hearing)
        _be_the_step(step, reservation.placement, log_filename, cores, saying)
        # unreachable: _be_the_step never returns

    os.close(saying)
    return RunningStep(step, reservation, pid, log_filename, started, hearing)


def _be_the_step(step, placement, log_filename, cores, saying) -> NoReturn:
    """
    Become the step, in the forked child, and never come back.

    Everything here is undoing something the child inherited that belongs to
    the scheduler.  The signal handlers are the scheduler's, so a Ctrl-C
    meant for one step would otherwise run the scheduler's shutdown in the
    child.  The file descriptors are the scheduler's, and are redirected by
    descriptor rather than by reassigning ``sys.stdout`` so that a model an
    MPI step launches writes to the log as well -- a launched command
    inherits the descriptor and knows nothing of Python's streams.

    It ends with ``os._exit``, which skips exit handlers and buffer flushes.
    Falling off the end or calling ``sys.exit`` would run the scheduler's
    ``atexit`` handlers in the child and flush buffers the scheduler still
    owns.
    """
    status = 1
    work_seconds = None
    try:
        for caught in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            signal.signal(caught, signal.SIG_DFL)

        if cores:
            try:
                os.sched_setaffinity(0, set(cores))
            except (AttributeError, OSError):
                # a platform without affinity, or cores the kernel will not
                # give us.  The step still runs; the scheduler's accounting
                # describes it and nothing enforces that, which is the same
                # footing memory is on.
                pass

        opened = os.open(
            log_filename, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644
        )
        os.dup2(opened, 1)
        os.dup2(opened, 2)
        os.close(opened)

        # and point Python's own streams at the descriptors just redirected.
        # Redirecting the descriptors is what catches a model an MPI step
        # launches, which knows nothing of Python's streams; rebinding these
        # is what catches Python's own writes when the parent's streams were
        # not the descriptors -- under pytest they are not, and neither are
        # they under anything else that captures output.
        sys.stdout = os.fdopen(1, 'w', buffering=1, closefd=False)
        sys.stderr = os.fdopen(2, 'w', buffering=1, closefd=False)

        os.chdir(step.work_dir)
        # this child *is* the separate process that flag asks for
        step.run_as_subprocess = False

        began = time.time()
        run_step_in_process(step, placement)
        work_seconds = time.time() - began
        status = 0
    except BaseException:  # noqa: BLE001
        # deliberately everything, including KeyboardInterrupt: this child
        # must not unwind into the scheduler's code on its way out
        traceback.print_exc()
    finally:
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except (OSError, ValueError):
            pass
        try:
            if work_seconds is not None:
                os.write(saying, f'{work_seconds}'.encode())
            os.close(saying)
        except OSError:
            pass
        os._exit(status)


def reap_one(running: Dict[str, 'RunningStep']) -> StepOutcome:
    """
    Wait for whichever step finishes next and say how it went.

    The scheduler reaps in its own loop rather than giving each running step
    a thread to wait on it.  A thread each is reasonable under `subprocess`
    and unsafe here: only the forking thread survives a fork, so a lock held
    by any other one at that moment is held forever in the child.

    Parameters
    ----------
    running : dict of polaris.run.executor.RunningStep
        The steps currently running, by path

    Returns
    -------
    outcome : polaris.run.executor.StepOutcome
        What happened to the one that finished
    """
    by_pid = {run.pid: (path, run) for path, run in running.items()}
    while True:
        pid, status = os.waitpid(-1, 0)
        if pid in by_pid:
            path, run = by_pid[pid]
            return _outcome(
                path,
                _returncode(status),
                time.time() - run.started,
                run.work_seconds(),
            )


def _returncode(status: int) -> int:
    """Read a wait status the way a return code reads: signals negative."""
    if os.WIFSIGNALED(status):
        return -os.WTERMSIG(status)
    if os.WIFEXITED(status):
        return os.WEXITSTATUS(status)
    return 1


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


def _outcome(
    step_path: str,
    returncode: int,
    seconds: float,
    work_seconds: Optional[float] = None,
) -> StepOutcome:
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
        work_seconds=work_seconds,
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
