"""
Handing out pieces of a step's work.

A step that hands out work is given a :py:class:`Pieces` in place of being
asked to ``run()``, and hands out its loops through it.  Each piece runs in
a child forked for it by the resident on the node of one of the step's
cores, bound to that core, with the step's work directory as its working
directory.  At most one piece runs on each core at a time, and the cores are
the step's own, reserved for it by the scheduler and given back when it
ends.

A fresh child for every piece is what MPAS-Analysis does on one node, and
the residents carry it across nodes.  Measured on Chrysalis, forking,
running and answering a piece costs about 18 ms, which is noise beside the
few seconds an analysis piece takes, and it means nothing one piece leaves
behind can reach the next.  What a piece cannot have is anything the step
set up in its own process: it starts from a fork of the resident, so what it
needs has to travel with it.

Functions are pickled by reference, so a piece must be a function a module
defines.  A lambda or a nested function is refused when it is handed out
rather than being pickled by value, which would quietly carry whatever it
closed over -- often the whole step -- to every piece.
"""

import os
import pickle
import time
from collections import deque
from multiprocessing.connection import Connection, wait
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple, cast

from polaris.run.connections import connect
from polaris.run.residents import ResidentDirectory

# a core a piece may run on: the node, as the allocation names it, and the
# core's id there
Slot = Tuple[str, int]


class PieceFailed(RuntimeError):
    """
    A piece of a step's work failed, or the process running it died.

    Attributes
    ----------
    index : int
        Which item of the call that handed it out the piece was for

    node : str
        The node it ran on

    log : str or None
        Where its output went, if it said anything
    """

    def __init__(self, message: str, index: int, node: str, log=None):
        super().__init__(message)
        self.index = index
        self.node = node
        self.log = log


class Pieces:
    """
    What a step hands out pieces of its work through.

    Attributes
    ----------
    slots : list of tuple of str and int
        The cores pieces run on, each as its node and its id there

    records : list of dict
        One record per piece handed out: where it ran, how long it took and
        how it ended, which is what a run reports the step's work from
    """

    def __init__(self, step, slots: List[Slot], directory: ResidentDirectory):
        """
        Parameters
        ----------
        step : polaris.Step
            The step handing out work, whose work directory the pieces run
            in and whose logger says what happened

        slots : list of tuple of str and int
            The cores reserved for the step, each as its node and its id

        directory : polaris.run.residents.ResidentDirectory
            How to reach the residents on those nodes
        """
        if not slots:
            raise ValueError(
                f'Step {step.path} hands out work but has no cores to hand '
                f'it out to.'
            )
        self.slots = list(slots)
        self.records: List[Dict[str, Any]] = []
        self._step = step
        self._directory = directory
        self._connections: Dict[str, Connection] = {}
        self._next_request = 0
        self._handed_out = 0

    @property
    def cores(self) -> int:
        """How many pieces may run at once."""
        return len(self.slots)

    def map(self, function: Callable, *iterables) -> List:
        """
        Run ``function`` once per item, each as a piece, and give back what
        each returned, in the order of the items.

        Parameters
        ----------
        function : callable
            A function a module defines, called with one item from each of
            ``iterables``, as the built-in ``map`` calls it

        *iterables : iterable
            What to call it with, which must all be the same length rather
            than being cut to the shortest

        Returns
        -------
        results : list
            What each call returned, in order

        Raises
        ------
        PieceFailed
            For the first piece that raised, or whose process died, once
            every other piece still running has been stopped
        """
        items = list(zip(*iterables, strict=True))
        if not items:
            return []
        work = [self._pickled(function, args) for args in items]

        results: List[Any] = [None] * len(items)
        pending: Deque[int] = deque(range(len(items)))
        free: Deque[Slot] = deque(self.slots)
        running: Dict[int, Tuple[int, Slot, Optional[str], float]] = {}
        failure: Optional[PieceFailed] = None

        nodes = {node for node, _ in self.slots}
        self._step.logger.info(
            f'handing out {len(items)} piece(s) of {_name(function)} over '
            f'{self.cores} core(s) on {len(nodes)} node(s)'
        )
        while running or (pending and failure is None):
            while pending and free and failure is None:
                index = pending.popleft()
                slot = free.popleft()
                try:
                    request_id, log = self._hand_out(work[index], slot)
                except (KeyError, EOFError, OSError) as error:
                    failure = _failure(
                        self._step,
                        function,
                        items[index],
                        index,
                        slot,
                        'unreachable',
                        {'error': error},
                        None,
                    )
                    self._cancel(running)
                    break
                running[request_id] = (index, slot, log, time.time())
            if not running:
                break

            for request_id, kind, payload in self._answers(running):
                index, slot, piece_log, started = running.pop(request_id)
                free.append(slot)
                self.records.append(
                    {
                        'node': slot[0],
                        'core': slot[1],
                        'seconds': round(time.time() - started, 3),
                        'outcome': kind,
                    }
                )
                if kind == 'done':
                    results[index] = payload['value']
                    continue
                if failure is None:
                    failure = _failure(
                        self._step,
                        function,
                        items[index],
                        index,
                        slot,
                        kind,
                        payload,
                        piece_log,
                    )
                    self._cancel(running)
        if failure is not None:
            raise failure
        return results

    def close(self) -> None:
        """Let go of the residents, which stops anything still running."""
        for conn in self._connections.values():
            try:
                conn.close()
            except OSError:
                pass
        self._connections.clear()
        # the residents remove the logs nothing was written to, which can
        # leave their directory empty
        try:
            os.rmdir(os.path.join(self._step.work_dir, 'pieces'))
        except OSError:
            pass

    def __enter__(self) -> 'Pieces':
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def _pickled(self, function: Callable, args: tuple) -> bytes:
        """Pickle one call, by reference, refusing what cannot be."""
        try:
            return pickle.dumps((function, args, {}))
        except (pickle.PicklingError, AttributeError, TypeError) as error:
            raise TypeError(
                f'Step {self._step.path} cannot hand out {_name(function)}: '
                f'a piece must be a function a module defines, called with '
                f'arguments that can be pickled ({error}).'
            ) from error

    def _hand_out(self, work: bytes, slot: Slot) -> Tuple[int, str]:
        """Ask the resident on a slot's node to fork one piece onto it."""
        node, core = slot
        self._next_request += 1
        # numbered from zero, so that in a step that calls map() once, item
        # 5 is piece_0005.log
        log = os.path.join(
            self._step.work_dir, 'pieces', f'piece_{self._handed_out:04d}.log'
        )
        self._handed_out += 1
        self._connection(node).send(
            (
                'piece',
                self._next_request,
                {
                    'work': work,
                    'cores': [core],
                    'work_dir': self._step.work_dir,
                    'log': log,
                },
            )
        )
        return self._next_request, log

    def _answers(self, running):
        """
        Wait for at least one answer, and give back every one there is.

        A resident whose connection closes has gone, and every piece it was
        running is answered for it as lost.
        """
        answers: List[Tuple[int, str, Any]] = []
        while not answers:
            nodes = {slot[0] for _, slot, _, _ in running.values()}
            ready = wait([self._connections[node] for node in nodes])
            for each_ready in ready:
                conn = cast(Connection, each_ready)
                node = next(
                    name
                    for name, each in self._connections.items()
                    if each is conn
                )
                try:
                    while True:
                        kind, request_id, payload = conn.recv()
                        if request_id in running:
                            answers.append((request_id, kind, payload))
                        if not conn.poll(0):
                            break
                except (EOFError, OSError):
                    self._connections.pop(node).close()
                    answered = {request_id for request_id, _, _ in answers}
                    for request_id, (_, slot, _, _) in running.items():
                        if slot[0] == node and request_id not in answered:
                            answers.append(
                                (request_id, 'lost', {'node': node})
                            )
        return answers

    def _cancel(self, running) -> None:
        """Stop every piece still running, after one has failed."""
        for request_id, (_, slot, _, _) in running.items():
            try:
                self._connection(slot[0]).send(('cancel', request_id, None))
            except (OSError, ValueError):
                pass

    def _connection(self, node: str) -> Connection:
        """The connection to the resident on a node, made once."""
        if node not in self._connections:
            self._connections[node] = connect(
                self._directory.address(node), self._directory.key
            )
        return self._connections[node]


def slots_from(placement) -> List[Slot]:
    """
    The cores a placement gives a step, as slots for its pieces.

    Parameters
    ----------
    placement : mache.parallel.ResourcePlacement
        Where the step's cores are

    Returns
    -------
    slots : list of tuple of str and int
        Each core as its node and its id there
    """
    nodes = list(placement.nodes) or [''] * len(placement.cores)
    return [
        (node, core)
        for node, cores in zip(nodes, placement.cores, strict=True)
        for core in cores
    ]


def _failure(step, function, args, index, slot, kind, payload, log):
    """Say which piece failed, where, and why."""
    node, core = slot
    call = f'{_name(function)}{_brief(args)}'
    where = f'on core {core} of node {node or "this node"}'
    if kind == 'failed':
        reason = f'raised {payload["kind"]}:\n{payload["error"].rstrip()}'
        log = payload.get('log') or log
    elif kind == 'died':
        reason = f'died with exit code {payload["returncode"]}'
    elif kind == 'lost':
        reason = 'was lost when the resident on its node went away'
    elif kind == 'unreachable':
        reason = f'could not be handed out: {payload["error"]}'
    else:
        reason = f'ended unexpectedly ({kind}: {payload})'
    message = f'Piece {index} of step {step.path}, {call} {where}, {reason}'
    if log is not None and os.path.exists(log):
        message = f'{message}\nIts output is in {log}'
    return PieceFailed(message, index=index, node=node, log=log)


def _name(function: Callable) -> str:
    return getattr(function, '__qualname__', repr(function))


def _brief(args: tuple, limit: int = 80) -> str:
    """The arguments of a call, short enough for an error message."""
    text = repr(args) if len(args) != 1 else f'({args[0]!r})'
    return text if len(text) <= limit else f'{text[: limit - 4]}...)'
