"""
Dask workers for a step whose arrays are spread over several nodes.

A step that hands out work can compute with Dask on its cores instead.  It
opens :py:meth:`polaris.run.pieces.Pieces.dask`, and the resident on each of
its nodes forks one Dask worker there, bound to the step's cores on that
node, with a thread for each core.  The scheduler runs in the step's own
process, and the workers go when the step closes them.

Three of Dask's defaults would absorb a failure, so each is changed: there
is no Nanny to restart a worker that dies, a task running on a worker that
dies fails rather than being retried elsewhere, and a step whose workers
have all gone fails rather than waiting for more.  A worker that dies fails
the step even when Dask finished its work elsewhere.  Every connection is
encrypted and authenticated with certificates made for the step.  There is
no dashboard: Dask opens an HTTP port on the scheduler and each worker
regardless, so it listens on this node only and serves nothing.
"""

import os
import pickle
import shutil
import time
from multiprocessing.connection import Connection, wait
from typing import Any, Dict, List, Optional, Set, Tuple, cast

import dask
import distributed
from distributed.security import Security

from polaris.run.confinement import _ranges, record_mismatch
from polaris.run.connections import bind_address, connect
from polaris.run.residents import ResidentDirectory

# how long the workers may take to start and reach their scheduler, in
# seconds
_START_SECONDS = 300.0

# how long a worker keeps trying to reach a scheduler it has lost, in
# seconds, after which it stops by itself
_DEATH_TIMEOUT = 60

# how long a task may wait with no worker left to run it before it fails,
# which is what keeps a step whose workers have all gone from waiting
# forever
_NO_WORKERS_TIMEOUT = '60s'

# how long to wait for the workers to go once they have been stopped, in
# seconds
_STOP_SECONDS = 60.0

# how long to wait for a resident's word on a worker the scheduler has
# already lost, in seconds
_LOST_SECONDS = 5.0

# where the scheduler's and the workers' HTTP servers listen, which Dask
# starts even with no dashboard, and what they serve
HTTP_ADDRESS = '127.0.0.1:0'
NO_ROUTES: List[str] = []


class WorkerLost(RuntimeError):
    """
    One of a step's Dask workers could not start, or died while the step
    held it.

    Attributes
    ----------
    node : str
        The node the worker was on

    log : str or None
        Where its output went
    """

    def __init__(self, message: str, node: str, log=None):
        super().__init__(message)
        self.node = node
        self.log = log


class DaskWorkers:
    """
    A step's Dask workers, one on each node its cores are on.

    Used as a context manager, whose value is the ``distributed.Client``
    the step computes through.  The workers are started on entering it and
    stopped on leaving it.

    Attributes
    ----------
    summary : dict or None
        How many workers there were, with how many threads, how long they
        took to start and how long the step held them, once they are gone
    """

    def __init__(
        self,
        step,
        cores: Dict[str, List[int]],
        directory: ResidentDirectory,
        interface: Optional[str] = None,
        memory: Optional[Dict[str, int]] = None,
    ):
        """
        Parameters
        ----------
        step : polaris.Step
            The step whose workers these are

        cores : dict of list of int
            The step's cores on each node, by node

        directory : polaris.run.residents.ResidentDirectory
            How to reach the residents on those nodes

        interface : str, optional
            The network interface the scheduler and workers listen on, or
            ``None`` for the one a node's hostname resolves to

        memory : dict of int, optional
            The memory in MiB each node's worker may hold, by node, or
            ``None`` for no limit
        """
        self.summary: Optional[Dict[str, Any]] = None
        self.open = False
        self._step = step
        self._cores = cores
        self._directory = directory
        self._interface = interface
        self._memory = memory or {}
        self._connections: Dict[str, Connection] = {}
        self._requests: Dict[str, int] = {}
        self._logs: Dict[str, str] = {}
        self._names: Dict[str, str] = {}
        self._lost: Dict[str, str] = {}
        self._gone: Set[str] = set()
        self._problems: List[str] = []
        self._cluster: Optional[distributed.LocalCluster] = None
        self._client: Optional[distributed.Client] = None
        self._config: Any = None
        self._began = 0.0
        self._ready = 0.0

    def __enter__(self) -> distributed.Client:
        self._began = time.time()
        security = Security.temporary()
        self._config = dask.config.set(
            {
                'distributed.scheduler.allowed-failures': 0,
                'distributed.scheduler.no-workers-timeout': (
                    _NO_WORKERS_TIMEOUT
                ),
                'distributed.scheduler.http.routes': NO_ROUTES,
            }
        )
        self._config.__enter__()
        self.open = True
        try:
            self._cluster = distributed.LocalCluster(
                n_workers=0,
                processes=False,
                protocol='tls://',
                host=bind_address(self._interface),
                security=security,
                dashboard_address=HTTP_ADDRESS,
                scheduler_kwargs={'dashboard': False},
                silence_logs=False,
            )
            self._ask_for_workers(security)
            self._wait_until_started()
            self._client = distributed.Client(self._cluster, security=security)
            self._client.wait_for_workers(
                len(self._requests), timeout=_START_SECONDS
            )
        except BaseException:
            self._stop()
            raise
        self._ready = time.time()
        threads = sum(len(cores) for cores in self._cores.values())
        self._step.logger.info(
            f'started {len(self._requests)} Dask worker(s) with {threads} '
            f'thread(s) in {self._ready - self._began:.1f} s'
        )
        return self._client

    def __exit__(self, kind, value, traceback) -> None:
        # a worker lost while the step computed fails the step, whatever
        # Dask made of it, including when the step caught what Dask raised
        self._collect_lost(self._missing())
        self._stop()
        if self._lost:
            node, reason = next(iter(self._lost.items()))
            others = len(self._lost) - 1
            message = (
                f'The Dask worker of step {self._step.path} on node '
                f'{node or "this node"} {reason}'
            )
            if others:
                message = f'{message}, and {others} more worker(s) were lost'
            log = self._logs.get(node)
            if log is not None and os.path.exists(log):
                message = f'{message}\nIts output is in {log}'
            raise WorkerLost(message, node=node, log=log) from value

    def _ask_for_workers(self, security: Security) -> None:
        """Ask the resident on each node to fork the step's worker there."""
        cluster = cast(distributed.LocalCluster, self._cluster)
        work_dir = self._step.work_dir
        for index, (node, cores) in enumerate(sorted(self._cores.items())):
            log = os.path.join(
                work_dir, 'dask', f'worker_{node or "local"}.log'
            )
            # nothing reserved means nothing to hold the worker to
            memory = self._memory.get(node) or 0
            name = f'{self._step.path}/{node or "local"}'
            payload = {
                'scheduler': cluster.scheduler_address,
                'security': pickle.dumps(security),
                'cores': list(cores),
                'name': name,
                'memory_limit': memory * 2**20,
                'local_directory': os.path.join(work_dir, 'dask'),
                'interface': self._interface,
                'death_timeout': _DEATH_TIMEOUT,
                'work_dir': work_dir,
                'log': log,
            }
            conn = connect(self._directory.address(node), self._directory.key)
            self._connections[node] = conn
            self._requests[node] = index
            self._logs[node] = log
            self._names[node] = name
            conn.send(('worker', index, payload))

    def _wait_until_started(self) -> None:
        """Wait for every worker to say it has started, or for one to fail."""
        started: Set[str] = set()
        deadline = time.time() + _START_SECONDS
        while len(started) < len(self._requests):
            remaining = deadline - time.time()
            if remaining <= 0:
                waiting = sorted(set(self._requests) - started)
                raise WorkerLost(
                    f'The Dask workers of step {self._step.path} on '
                    f'{", ".join(node or "this node" for node in waiting)} '
                    f'did not start within {_START_SECONDS:.0f} s.',
                    node=waiting[0],
                )
            for node, kind, payload in self._answers(remaining):
                if kind == 'started':
                    started.add(node)
                    self._check_where(node, payload.get('where') or {})
                    continue
                reason = _reason(kind, payload)
                raise WorkerLost(
                    f'The Dask worker of step {self._step.path} on node '
                    f'{node or "this node"} could not start: it {reason}',
                    node=node,
                    log=self._logs.get(node),
                )

    def _missing(self) -> List[str]:
        """
        The nodes whose worker the scheduler no longer has.

        A scheduler that cannot be asked names none, leaving the residents
        to say which workers ended.
        """
        if self._client is None:
            return []
        try:
            workers = self._client.scheduler_info()['workers'].values()
        except (OSError, TimeoutError, KeyError):
            return []
        names = {worker.get('name') for worker in workers}
        return [
            node for node in self._requests if self._names[node] not in names
        ]

    def _collect_lost(self, missing: List[str]) -> None:
        """
        Note every worker that has died, or whose resident has gone.

        The scheduler can notice a worker has gone before the resident that
        forked it has said how, so word on those the scheduler has lost is
        waited for a little.
        """
        deadline = time.time() + _LOST_SECONDS
        while self._connections:
            waiting = any(node not in self._gone for node in missing)
            remaining = deadline - time.time() if waiting else 0.0
            answers = self._answers(max(remaining, 0.0))
            for node, kind, payload in answers:
                # a worker that raised has also died, and its traceback
                # says more than its exit code
                if kind != 'started' and node not in self._lost:
                    self._lost[node] = _reason(kind, payload)
            if not answers and remaining <= 0:
                break
        for node in missing:
            if node not in self._lost:
                self._lost[node] = 'was lost by the Dask scheduler'

    def _answers(self, timeout: float) -> List[Tuple[str, str, Any]]:
        """What the residents have said about the workers, by node."""
        by_conn = {conn: node for node, conn in self._connections.items()}
        answers: List[Tuple[str, str, Any]] = []
        for ready in wait(list(by_conn), timeout=timeout):
            conn = cast(Connection, ready)
            node = by_conn[conn]
            try:
                while True:
                    kind, _, payload = conn.recv()
                    answers.append((node, kind, payload))
                    if kind == 'died':
                        self._gone.add(node)
                    if not conn.poll(0):
                        break
            except (EOFError, OSError):
                del self._connections[node]
                conn.close()
                self._gone.add(node)
                answers.append((node, 'lost', {}))
        return answers

    def _check_where(self, node: str, where: dict) -> None:
        """Hold the cores a worker was allowed against those it was given."""
        cores = where.get('cores')
        given = sorted(self._cores[node])
        if cores is not None and cores != given:
            self._problems.append(
                f'The Dask worker given cores {_ranges(given)} on '
                f'{node or "this node"} was allowed {len(cores)} '
                f'({_ranges(cores)}).'
            )

    def stop(self) -> None:
        """
        Stop the workers, if the step has not already left the context.

        Their being lost is not reported: this is for tidying up after a
        step that went wrong some other way.
        """
        if self.open:
            self._stop()

    def _stop(self) -> None:
        """Close the client and scheduler, and stop and reap the workers."""
        stopping = time.time()
        # each is closed even if one before it fails to close, so that the
        # workers are always stopped and reaped
        for closing in (self._client, self._cluster):
            if closing is None:
                continue
            try:
                closing.close()
            except Exception as error:  # noqa: BLE001
                self._step.logger.warning(f'closing {closing}: {error!r}')
        self._client = None
        self._cluster = None
        if self._config is not None:
            self._config.__exit__(None, None, None)
            self._config = None
        for node, conn in self._connections.items():
            if node in self._gone:
                continue
            try:
                conn.send(('cancel', self._requests[node], None))
            except (OSError, ValueError):
                pass
        # a worker's end is always reported, so each one's is awaited, so
        # that its cores are free before the step gives them back
        deadline = time.time() + _STOP_SECONDS
        while set(self._connections) - self._gone:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            self._answers(remaining)
        for conn in self._connections.values():
            conn.close()
        self._connections.clear()
        if self._problems:
            record_mismatch(self._step, self._problems, self._step.logger)
            self._problems = []
        shutil.rmtree(
            os.path.join(self._step.work_dir, 'dask', 'dask-scratch-space'),
            ignore_errors=True,
        )
        if self.open:
            threads = sum(len(cores) for cores in self._cores.values())
            self.summary = {
                'workers': len(self._requests),
                'threads': threads,
                'start_seconds': round(
                    (self._ready or stopping) - self._began, 3
                ),
                'held_seconds': round(stopping - self._began, 3),
                'failed': bool(self._lost) or not self._ready,
            }
        self.open = False


def _reason(kind: str, payload: Any) -> str:
    """Say how a worker ended, as the end of a sentence."""
    if kind == 'failed':
        return f'raised {payload["kind"]}:\n{payload["error"].rstrip()}'
    if kind == 'died':
        return f'died with exit code {payload["returncode"]}'
    if kind == 'lost':
        return 'was lost when the resident on its node went away'
    return f'ended unexpectedly ({kind}: {payload})'
