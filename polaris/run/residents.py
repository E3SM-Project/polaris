"""
Starting, finding and stopping a run's residents.

A run that has work for the residents starts one on each node it uses, and
this is the run's side of them.  The run listens; each resident connects,
says hello with the address it listens on for steps, and keeps that
connection open for as long as it lives.  The connection is how a resident
knows the run is still there -- it exits when the connection closes -- and
how the run knows a resident has gone.

A step that hands out work does not go through the run to reach a resident.
It is given a :py:class:`ResidentDirectory` and connects to the residents it
needs itself, so a step behaves the same whether `polaris serial` or
`polaris parallel` is running it.
"""

import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from multiprocessing import AuthenticationError
from multiprocessing.connection import Connection, wait
from typing import Dict, List, Optional, Sequence, Tuple, cast

from mache.parallel import ResourcePlacement

from polaris.run.connections import (
    KEY_VARIABLE,
    Address,
    accept,
    listen,
    listening_socket,
    new_key,
)
from polaris.run.resident import fork, serve

# how long a resident that was told to stop is given to go before it is
# killed
_STOP_SECONDS = 10.0


@dataclass(frozen=True)
class ResidentDirectory:
    """
    What a step needs to reach a run's residents.

    Attributes
    ----------
    key : bytes
        The run's key, without which a resident refuses a connection

    addresses : dict
        Where the resident on each node listens, keyed by node name
    """

    key: bytes
    addresses: Dict[str, Address]

    def address(self, node: str) -> Address:
        """
        Where the resident on a node listens.

        Parameters
        ----------
        node : str
            The node, as the allocation names it.  An empty name, which is
            how a placement names the only node of a run that has no
            allocation to name, means the only resident there is.

        Returns
        -------
        address : tuple of str and int
            The resident's host and port
        """
        if node == '' and len(self.addresses) == 1:
            return next(iter(self.addresses.values()))
        short = _short(node)
        for name, address in self.addresses.items():
            if _short(name) == short:
                return address
        raise KeyError(f'No resident is running on node {node!r}.')


class Residents:
    """
    A run's side of its residents.

    Attributes
    ----------
    key : bytes
        The run's key

    addresses : dict
        Where each resident that said hello listens, by node

    facts : dict
        What each resident said about itself when it said hello, by node

    lost : dict
        The nodes whose residents went away, and when
    """

    def __init__(self, interface: Optional[str] = None):
        """
        Parameters
        ----------
        interface : str, optional
            The network interface to listen on and to have residents listen
            on, such as ``ib0``
        """
        self.key = new_key()
        self.interface = interface
        self.addresses: Dict[str, Address] = {}
        self.facts: Dict[str, dict] = {}
        self.lost: Dict[str, float] = {}
        self.started: Optional[float] = None
        self.ready_at: Optional[float] = None
        self._registry = listen(self.key, interface)
        self._socket = listening_socket(self._registry)
        self._expected: List[str] = []
        self._control: Dict[str, Connection] = {}
        self._local: Dict[int, str] = {}
        self._launcher: Optional[subprocess.Popen] = None
        self._launch_log: Optional[str] = None
        self.launcher_returncode: Optional[int] = None

    @property
    def registry(self) -> Address:
        """Where residents say hello."""
        return cast(Address, self._registry.address)

    @property
    def directory(self) -> ResidentDirectory:
        """What a step needs to reach the residents ready so far."""
        return ResidentDirectory(key=self.key, addresses=dict(self.addresses))

    @property
    def ready(self) -> bool:
        """Whether every resident that was started has said hello."""
        said = {_short(node) for node in self.addresses}
        return bool(self._expected) and all(
            _short(node) in said for node in self._expected
        )

    def start_local(self, names: List[str]) -> None:
        """
        Fork a resident on this node for each name.

        A resident forked here inherits everything this process imported, so
        it is ready at once.  This is how a run with one node, or none,
        starts its resident, and how the tests start several on one machine.

        Parameters
        ----------
        names : list of str
            The node each resident speaks for
        """
        if self.started is None:
            self.started = time.time()
        for name in names:
            self._expected.append(name)
            keep_out = [self._registry, *self._control.values()]
            pid = fork(
                serve,
                (self.registry, self.key, name, self.interface),
                keep_out,
            )
            self._local[pid] = name

    def launch(
        self,
        parallel_system,
        names: List[str],
        core_id: int,
        log_filename: str,
        preload: Sequence[str] = ('polaris.tasks',),
    ) -> List[str]:
        """
        Start a resident on every node of an allocation, with one launch.

        The launch has one rank per node, confined by placement to one core
        on each, so the rest of the allocation stays usable.  A resident's
        children are bound to other cores by the resident itself, which
        works where a launch is confined by affinity, as on Chrysalis; where
        a launch is confined by a cgroup instead, its children could not
        leave it, and that is still to be measured.

        The run's key reaches the residents through the environment, which
        other users on a node cannot read, rather than on the command line,
        which they can.

        Parameters
        ----------
        parallel_system : mache.parallel.ParallelSystem
            What renders the launch

        names : list of str
            The nodes, as the allocation names them

        core_id : int
            The core each resident is confined to on its node

        log_filename : str
            Where the launch's output goes

        preload : sequence of str, optional
            Modules each resident imports once, before forking anything

        Returns
        -------
        command : list of str
            The launch, as rendered
        """
        if self.started is None:
            self.started = time.time()
        self._expected.extend(names)
        args = [sys.executable, '-m', 'polaris.run.resident']
        host, port = self.registry
        args.append(f'{host}:{port}')
        if self.interface:
            args.extend(['--interface', self.interface])
        args.append('--preload')
        args.extend(preload)
        placement = ResourcePlacement(
            nodes=tuple(names),
            cores=tuple((core_id,) for _ in names),
            gpus=0,
        )
        command = parallel_system.get_parallel_command(
            args=args,
            ntasks=len(names),
            cpus_per_task=1,
            placement=placement,
        )
        environ = dict(os.environ)
        environ[KEY_VARIABLE] = self.key.hex()
        os.makedirs(os.path.dirname(log_filename) or '.', exist_ok=True)
        self._launch_log = log_filename
        with open(log_filename, 'w') as log:
            self._launcher = subprocess.Popen(
                command, env=environ, stdout=log, stderr=subprocess.STDOUT
            )
        return command

    def sources(self) -> list:
        """What a loop should wait on to hear from the residents."""
        return [self._socket, *self._control.values()]

    def inherited(self) -> list:
        """
        What a process forked from this one must close: the run's side of
        its residents, which belongs to the run and not to a step.

        A step that kept them open would keep a resident from noticing that
        the run had gone.
        """
        return [self._registry, *self._control.values()]

    def hear(self, source) -> Optional[Tuple[str, str]]:
        """
        Act on a source from :py:meth:`sources` that has something to say.

        Parameters
        ----------
        source : object
            The socket or connection that ``wait()`` returned

        Returns
        -------
        note : tuple of str or None
            What changed: ``('ready', node)`` when a resident said hello,
            ``('lost', node)`` when one went away, or ``None``
        """
        if source is self._socket:
            return self._welcome()
        for node, conn in list(self._control.items()):
            if conn is source:
                try:
                    conn.recv()
                except (EOFError, OSError):
                    self._lose(node)
                    return ('lost', node)
                return None
        return None

    def wait_until_ready(self, timeout: float) -> None:
        """
        Wait until every resident that was started has said hello.

        Parameters
        ----------
        timeout : float
            How long to wait, in seconds

        Raises
        ------
        RuntimeError
            If a resident went away before saying hello, or not every one
            said hello in time
        """
        deadline = time.time() + timeout
        while not self.ready:
            self._reap_local()
            self._poll_launcher()
            if self.launcher_returncode is not None:
                raise RuntimeError(
                    f'The launch that starts the residents exited with '
                    f'{self.launcher_returncode} before every resident said '
                    f'hello. See {self._launch_log}.'
                )
            if self.lost:
                raise RuntimeError(
                    f'Resident(s) on {sorted(self.lost)} went away before '
                    f'the run could use them.'
                )
            remaining = deadline - time.time()
            if remaining <= 0:
                missing = sorted(
                    set(map(_short, self._expected))
                    - set(map(_short, self.addresses))
                )
                raise RuntimeError(
                    f'{len(self.addresses)} of {len(self._expected)} '
                    f'resident(s) said hello in {timeout:.0f} s; still '
                    f'waiting on {missing}.'
                )
            for source in wait(self.sources(), timeout=min(remaining, 1.0)):
                self.hear(source)

    def owns(self, pid: int) -> bool:
        """
        Whether a child process of this one is a resident or their launch.

        A loop that reaps any child that has exited has to know these, or it
        would reap them as strangers and nothing would notice they had gone.
        """
        if self._launcher is not None and pid == self._launcher.pid:
            return True
        return pid in self._local

    def exited(
        self, pid: int, returncode: Optional[int] = None
    ) -> Optional[Tuple[str, str]]:
        """
        Note that a resident forked here, or the launch, has exited and
        been reaped.

        Parameters
        ----------
        pid : int
            The process id

        returncode : int, optional
            How it exited, if whoever reaped it knows

        Returns
        -------
        note : tuple of str or None
            What changed: ``('launch_ended', returncode)`` or
            ``('lost', node)``, or ``None``
        """
        if self._launcher is not None and pid == self._launcher.pid:
            self.launcher_returncode = 1 if returncode is None else returncode
            return ('launch_ended', str(self.launcher_returncode))
        name = self._local.pop(pid, None)
        if name is not None and name not in self.lost:
            self._lose(name)
            return ('lost', name)
        return None

    def stop(self) -> None:
        """Tell every resident to stop, and make sure they have."""
        # residents that never said hello cannot be told, so there is
        # nothing to wait for before ending their launch
        told = bool(self._control)
        for conn in self._control.values():
            try:
                conn.send(('stop', None, None))
            except (OSError, ValueError):
                pass
            conn.close()
        self._control.clear()

        deadline = time.time() + _STOP_SECONDS
        while self._local and time.time() < deadline:
            self._reap_local()
            if self._local:
                time.sleep(0.05)
        for pid in list(self._local):
            try:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
            except (ProcessLookupError, ChildProcessError):
                pass
            self._local.pop(pid, None)
        self._stop_launcher(deadline if told else time.time())
        self._registry.close()

    def __enter__(self) -> 'Residents':
        return self

    def __exit__(self, *args) -> None:
        self.stop()

    def _welcome(self) -> Optional[Tuple[str, str]]:
        """Take a resident's hello."""
        try:
            conn = accept(self._registry)
            kind, _, facts = conn.recv()
        except (AuthenticationError, EOFError, OSError):
            # someone without the run's key, or a resident that died at once
            return None
        if kind != 'hello':
            conn.close()
            return None
        node = facts['node']
        self._control[node] = conn
        self.addresses[node] = tuple(facts['address'])
        self.facts[node] = facts
        if self.ready and self.ready_at is None:
            self.ready_at = time.time()
        return ('ready', node)

    def _lose(self, node: str) -> None:
        """Note that a resident has gone, so that nothing is sent to it."""
        self.lost[node] = time.time()
        self.addresses.pop(node, None)
        conn = self._control.pop(node, None)
        if conn is not None:
            conn.close()

    def _stop_launcher(self, deadline: float) -> None:
        """
        Let the launch end, and end it if it will not.

        The residents exit once told to stop, and the launch with them.  One
        that has not by the deadline is terminated, which the batch system
        passes on to every resident it started, and their children go with
        them.
        """
        if self._launcher is None or self.launcher_returncode is not None:
            return
        try:
            self.launcher_returncode = self._launcher.wait(
                timeout=max(deadline - time.time(), 0.1)
            )
            return
        except subprocess.TimeoutExpired:
            pass
        self._launcher.terminate()
        try:
            self.launcher_returncode = self._launcher.wait(
                timeout=_STOP_SECONDS
            )
        except subprocess.TimeoutExpired:
            self._launcher.kill()
            self.launcher_returncode = self._launcher.wait()

    def _poll_launcher(self) -> None:
        """Notice that the launch has exited, where nothing else reaps it."""
        if self._launcher is not None and self.launcher_returncode is None:
            self.launcher_returncode = self._launcher.poll()

    def _reap_local(self) -> None:
        """Notice residents forked here that have already exited."""
        for pid in list(self._local):
            try:
                done, _ = os.waitpid(pid, os.WNOHANG)
            except ChildProcessError:
                done = pid
            if done == pid:
                self.exited(pid)


def _short(name: str) -> str:
    """A node's short name, which is how a resident names its node."""
    return name.split('.')[0]


def resident_options(config):
    """
    How a run's residents are to be started: the network interface to use,
    and how long to wait for them.

    Work directories set up before these options existed are read with
    their defaults.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        The run's config

    Returns
    -------
    interface : str or None
        The network interface, or ``None`` for the one a node's hostname
        resolves to

    start_timeout : float
        How long to wait for every resident to say hello, in seconds
    """
    interface = None
    start_timeout = 1800.0
    if config.has_option('residents', 'interface'):
        interface = config.get('residents', 'interface').strip() or None
    if config.has_option('residents', 'start_timeout'):
        start_timeout = config.getfloat('residents', 'start_timeout')
    return interface, start_timeout
