"""
A resident Polaris process: one on each node, importing once and then only
forking.

The scheduler forks a child for each step it starts, which is cheap because
the child inherits everything the scheduler imported, and confined, because
a process can only fork on the node it runs on.  A resident is that same
cheap fork made available on another node.  It imports Polaris once -- the
cost the scheduler pays once per run, paid here once per node and in
parallel -- and after that it only forks.

It must start no thread to fork safely, which is why it does nothing else:
anything that starts a thread does so in a child.  Only the forking thread
survives a fork, so a lock held by any other thread at that moment is held
forever in the child.  The one other thread a resident has is jemalloc's
background thread, which importing Polaris starts and which jemalloc keeps
safe across a fork; the scheduler forks beside the same thread.

What it forks is decided elsewhere.  A step that hands out work connects and
asks for a piece of that work to be forked onto one of its cores; the
resident forks it, and passes back what the child says without reading it.
A resident is asked to fork; it does not decide what runs.

Nothing it forks outlives it.  Each child asks the kernel to kill it if the
resident dies first, and a resident whose connection to its run closes kills
its children and exits.
"""

import argparse
import ctypes
import importlib
import logging
import os
import pickle
import signal
import socket
import sys
import time
import traceback
import warnings
from multiprocessing import AuthenticationError
from multiprocessing.connection import Connection, Listener, Pipe, wait
from typing import Dict, List, Optional, Union

import psutil

from polaris.run.connections import (
    KEY_VARIABLE,
    Address,
    accept,
    connect,
    listen,
    listening_socket,
)

# how long the loop waits before looking for children that have exited.  A
# child's exit normally announces itself at once, by closing its pipe, so
# this only bounds how long a quiet death goes unnoticed.
_HOUSEKEEPING_SECONDS = 1.0

# prctl's request to be sent a signal when the parent dies
_PR_SET_PDEATHSIG = 1


def main():
    """Run a resident, as ``python -m polaris.run.resident <registry>``."""
    parser = argparse.ArgumentParser(
        description='Run a resident Polaris process on this node',
        prog='python -m polaris.run.resident',
    )
    parser.add_argument(
        'registry', help='Where to say hello to the run, as host:port'
    )
    parser.add_argument(
        '--interface',
        default=None,
        help='The network interface to listen on, such as ib0',
    )
    parser.add_argument(
        '--preload',
        nargs='*',
        default=['polaris.tasks'],
        help='Modules to import once, before anything is forked',
    )
    args = parser.parse_args()

    # Python warns about forking beside jemalloc's thread, which is safe (see
    # above), and shows the warning by default only in code run as
    # __main__, as this module is.  The scheduler forks without it.
    warnings.filterwarnings(
        'ignore',
        message=r'This process .* is multi-threaded',
        category=DeprecationWarning,
    )

    for module in args.preload:
        importlib.import_module(module)

    key = bytes.fromhex(os.environ.pop(KEY_VARIABLE))
    host, _, port = args.registry.rpartition(':')
    serve((host, int(port)), key, _short_hostname(), args.interface)


def serve(
    registry: Address, key: bytes, name: str, interface: Optional[str] = None
) -> None:
    """
    Say hello to the run, then fork what is asked for until told to stop.

    Returns when the run says to stop or its connection closes, having
    killed and reaped every child.

    Parameters
    ----------
    registry : tuple of str and int
        Where the run listens for its residents

    key : bytes
        The run's key

    name : str
        The node this resident speaks for, as the allocation names it

    interface : str, optional
        The network interface to listen on for steps
    """
    listener = listen(key, interface)
    control = connect(registry, key)
    control.send(
        (
            'hello',
            None,
            {
                'node': name,
                'address': listener.address,
                'pid': os.getpid(),
                'threads': _thread_count(),
                'ready_after': _seconds_since_start(),
            },
        )
    )
    resident = _Resident(control, listener)
    try:
        resident.loop()
    finally:
        resident.close()


def die_with_parent(parent: int) -> None:
    """
    Have the kernel kill this process when the one that forked it dies.

    Called first thing in a child, so that nothing a resident forked can
    outlive it however the resident ends.  Where the kernel offers no such
    request, the child carries on without it.

    Parameters
    ----------
    parent : int
        The process id of the parent, read before forking, so that a parent
        that died before this was asked can be noticed
    """
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        libc.prctl(_PR_SET_PDEATHSIG, signal.SIGKILL)
    except (AttributeError, OSError):
        return
    if os.getppid() != parent:
        os._exit(1)


class _Child:
    """A child this resident forked, and whom to tell how it went."""

    def __init__(
        self,
        client: Connection,
        request_id,
        reader: Connection,
        log: Optional[str] = None,
    ):
        self.client = client
        self.request_id = request_id
        self.reader: Optional[Connection] = reader
        self.log = log
        self.answered = False


class _Resident:
    """The state of one resident's loop."""

    def __init__(self, control: Connection, listener: Listener):
        self.control = control
        self.listener = listener
        self.socket = listening_socket(listener)
        self.clients: List[Connection] = []
        self.children: Dict[int, _Child] = {}
        self.readers: Dict[Connection, int] = {}

    def loop(self) -> None:
        """Serve the run, the steps and the children until told to stop."""
        while True:
            sources: List[Union[Connection, socket.socket]] = [
                self.control,
                self.socket,
                *self.clients,
                *self.readers,
            ]
            for source in wait(sources, timeout=_HOUSEKEEPING_SECONDS):
                if source is self.control:
                    if not self._hear_from_run():
                        return
                elif source is self.socket:
                    self._accept()
                elif source in self.readers:
                    self._relay(source)
                elif source in self.clients:
                    self._hear_from_client(source)
            self._reap()

    def close(self) -> None:
        """Kill and reap every child, and close every connection."""
        for pid in list(self.children):
            _kill(pid)
        for _ in list(self.children):
            try:
                os.waitpid(-1, 0)
            except ChildProcessError:
                break
        for child in self.children.values():
            _kept(child.log)
        self.children.clear()
        for conn in [self.control, *self.clients, *self.readers]:
            _close(conn)
        _close(self.listener)

    def _hear_from_run(self) -> bool:
        """Read what the run said; say whether to keep going."""
        try:
            kind, _, _ = self.control.recv()
        except (EOFError, OSError):
            return False
        return kind != 'stop'

    def _accept(self) -> None:
        """Take a connection from a step that hands out work."""
        try:
            self.clients.append(accept(self.listener))
        except (AuthenticationError, EOFError, OSError):
            # someone without the run's key, or a step that gave up
            pass

    def _hear_from_client(self, client: Connection) -> None:
        """Act on one request from a step."""
        try:
            kind, request_id, payload = client.recv()
        except (EOFError, OSError):
            self._drop(client)
            return
        if kind == 'piece':
            self._fork_piece(client, request_id, payload)
        elif kind == 'cancel':
            for pid, child in self.children.items():
                if child.client is client and child.request_id == request_id:
                    _kill(pid)
        else:
            self._send(
                client, ('error', request_id, f'unknown request {kind!r}')
            )

    def _fork_piece(self, client: Connection, request_id, payload) -> None:
        """Fork one piece of a step's work."""
        reader, writer = Pipe(duplex=False)
        keep_out = [reader, self.control, self.listener]
        keep_out.extend(self.clients)
        keep_out.extend(self.readers)
        pid = fork(_run_piece, (writer, request_id, payload), keep_out)
        writer.close()
        self.children[pid] = _Child(
            client, request_id, reader, payload.get('log')
        )
        self.readers[reader] = pid

    def _relay(self, reader: Connection) -> None:
        """Pass on what a child said, without reading it."""
        child = self.children.get(self.readers[reader])
        try:
            message = reader.recv_bytes()
        except (EOFError, OSError):
            # the child has exited or closed its end
            del self.readers[reader]
            _close(reader)
            if child is not None:
                child.reader = None
            return
        if child is not None and not child.answered:
            child.answered = True
            self._send(child.client, message, raw=True)

    def _reap(self) -> None:
        """Say which children have exited without a word, and how."""
        while True:
            try:
                pid, status = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                return
            if pid == 0:
                return
            child = self.children.get(pid)
            if child is None:
                continue
            # a child that answered and exited at once can be reaped before
            # its answer is read, so its pipe is drained -- while it is
            # still known, so that the answer is passed on -- before
            # deciding it said nothing
            while (
                not child.answered
                and child.reader is not None
                and child.reader.poll(0)
            ):
                self._relay(child.reader)
            del self.children[pid]
            if not child.answered:
                child.answered = True
                # a child that ended without a word never got to remove its
                # log if it was empty, so that is done here, before the
                # step hears of it
                log = _kept(child.log)
                self._send(
                    child.client,
                    (
                        'died',
                        child.request_id,
                        {
                            'pid': pid,
                            'returncode': _returncode(status),
                            'log': log,
                        },
                    ),
                )

    def _drop(self, client: Connection) -> None:
        """Forget a step that went away, and stop what it was running."""
        if client in self.clients:
            self.clients.remove(client)
        for pid, child in self.children.items():
            if child.client is client:
                _kill(pid)
        _close(client)

    def _send(self, client: Connection, message, raw=False) -> None:
        """Tell a step something, dropping it if it has gone."""
        try:
            if raw:
                client.send_bytes(message)
            else:
                client.send(message)
        except (OSError, ValueError):
            self._drop(client)


def fork(target, args, keep_out) -> int:
    """
    Fork a child that runs ``target(*args)`` and never comes back.

    Everything the child is given that belongs to its parent -- the
    connections in ``keep_out``, the signal handlers -- is let go first, so
    that a child cannot answer for its parent or outlive it.

    Parameters
    ----------
    target : callable
        What the child runs

    args : tuple
        What it is called with

    keep_out : list
        Connections and listeners the child must not hold

    Returns
    -------
    pid : int
        The child's process id, in the parent
    """
    sys.stdout.flush()
    sys.stderr.flush()
    parent = os.getpid()
    pid = os.fork()
    if pid != 0:
        return pid

    status = 1
    try:
        die_with_parent(parent)
        for each in keep_out:
            _close(each)
        signal.set_wakeup_fd(-1)
        for caught in (
            signal.SIGINT,
            signal.SIGTERM,
            signal.SIGHUP,
            signal.SIGCHLD,
        ):
            signal.signal(caught, signal.SIG_DFL)
        target(*args)
        status = 0
    except BaseException:  # noqa: BLE001
        # deliberately everything: this child must not unwind into its
        # parent's code on its way out
        traceback.print_exc()
    finally:
        os._exit(status)


def _run_piece(writer: Connection, request_id, payload) -> None:
    """Be one piece of a step's work: run it, and say how it went."""
    began = time.time()
    log = payload.get('log')
    try:
        # output first, so that a failure in what follows lands in the log
        if log:
            _write_output_to(log)
        cores = payload.get('cores')
        if cores:
            try:
                os.sched_setaffinity(0, cores)
            except (AttributeError, OSError):
                # cores the kernel will not give: the piece still runs, and
                # where it ran says so, to be reported rather than fatal
                pass
        if payload.get('work_dir'):
            os.chdir(payload['work_dir'])
        function, args, kwargs = pickle.loads(payload['work'])
        value = function(*args, **kwargs)
        sys.stdout.flush()
        sys.stderr.flush()
        message = pickle.dumps(
            (
                'done',
                request_id,
                {
                    'value': value,
                    'seconds': time.time() - began,
                    'pid': os.getpid(),
                    'log': _kept(log),
                    'where': _where(),
                },
            )
        )
    except BaseException as exception:  # noqa: BLE001
        # deliberately everything: a piece that calls sys.exit() has failed
        # as surely as one that raises, and should say so
        error = traceback.format_exc()
        sys.stderr.write(error)
        sys.stderr.flush()
        message = pickle.dumps(
            (
                'failed',
                request_id,
                {
                    'error': error,
                    'kind': type(exception).__name__,
                    'pid': os.getpid(),
                    'log': log,
                    'where': _where(),
                },
            )
        )
    writer.send_bytes(message)


def _where() -> dict:
    """Where this piece ran: the host, and the cores it was allowed."""
    try:
        cores = sorted(os.sched_getaffinity(0))
    except AttributeError:
        cores = []
    return {'host': _short_hostname(), 'cores': cores}


def _write_output_to(log: str) -> None:
    """Send this process's output, and its logging, to a piece's log."""
    os.makedirs(os.path.dirname(log) or '.', exist_ok=True)
    opened = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    os.dup2(opened, 1)
    os.dup2(opened, 2)
    os.close(opened)
    sys.stdout = os.fdopen(1, 'w', buffering=1, closefd=False)
    sys.stderr = os.fdopen(2, 'w', buffering=1, closefd=False)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, force=True)


def _kept(log: Optional[str]) -> Optional[str]:
    """
    Keep a piece's log only if something was written to it.

    A step may hand out dozens of pieces, most of which say nothing, and an
    empty file for each is clutter in the step's work directory.
    """
    if log is None:
        return None
    try:
        if os.path.getsize(log) == 0:
            os.remove(log)
            return None
    except OSError:
        return None
    return log


def _returncode(status: int) -> int:
    """Read a wait status the way a return code reads: signals negative."""
    if os.WIFSIGNALED(status):
        return -os.WTERMSIG(status)
    if os.WIFEXITED(status):
        return os.WEXITSTATUS(status)
    return 1


def _kill(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _close(each) -> None:
    try:
        each.close()
    except OSError:
        pass


def _thread_count() -> int:
    """How many OS threads this process holds, as the kernel counts them."""
    try:
        return len(os.listdir('/proc/self/task'))
    except OSError:
        return -1


def _seconds_since_start() -> float:
    """How long ago this process started, which is mostly imports."""
    return round(time.time() - psutil.Process().create_time(), 2)


def _short_hostname() -> str:
    return socket.gethostname().split('.')[0]


if __name__ == '__main__':
    main()
