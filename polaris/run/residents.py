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
import time
from dataclasses import dataclass
from multiprocessing import AuthenticationError
from multiprocessing.connection import Connection, wait
from typing import Dict, List, Optional, cast

from polaris.run.connections import (
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

    def sources(self) -> list:
        """What a loop should wait on to hear from the residents."""
        return [self._socket, *self._control.values()]

    def hear(self, source) -> None:
        """
        Act on a source from :py:meth:`sources` that has something to say.

        Parameters
        ----------
        source : object
            The socket or connection that ``wait()`` returned
        """
        if source is self._socket:
            self._welcome()
            return
        for node, conn in list(self._control.items()):
            if conn is source:
                try:
                    conn.recv()
                except (EOFError, OSError):
                    self._lose(node)
                return

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
        """Whether a child process of this one is one of the residents."""
        return pid in self._local

    def exited(self, pid: int) -> None:
        """
        Note that a resident forked here has exited and been reaped.

        Parameters
        ----------
        pid : int
            The resident's process id
        """
        name = self._local.pop(pid, None)
        if name is not None and name not in self.lost:
            self._lose(name)

    def stop(self) -> None:
        """Tell every resident to stop, and make sure they have."""
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
        self._registry.close()

    def __enter__(self) -> 'Residents':
        return self

    def __exit__(self, *args) -> None:
        self.stop()

    def _welcome(self) -> None:
        """Take a resident's hello."""
        try:
            conn = accept(self._registry)
            kind, _, facts = conn.recv()
        except (AuthenticationError, EOFError, OSError):
            # someone without the run's key, or a resident that died at once
            return
        if kind != 'hello':
            conn.close()
            return
        node = facts['node']
        self._control[node] = conn
        self.addresses[node] = tuple(facts['address'])
        self.facts[node] = facts
        if self.ready and self.ready_at is None:
            self.ready_at = time.time()

    def _lose(self, node: str) -> None:
        """Note that a resident has gone, so that nothing is sent to it."""
        self.lost[node] = time.time()
        self.addresses.pop(node, None)
        conn = self._control.pop(node, None)
        if conn is not None:
            conn.close()

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
