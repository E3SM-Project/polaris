"""
A record of what the scheduler decided, and when.

A concurrent run that is slower than expected is very hard to diagnose from
step logs alone, because the interesting question -- why was nothing running
at this moment -- is not a question about any one step.  Answering it needs
the decisions themselves: what became ready, what was started, what was held
back and for want of what.

The records are one JSON object per line so that they can be read while the
run is still going and appended to without rewriting anything.  Every record
carries the seconds since the run began, because what matters afterwards is
almost always when something happened relative to everything else rather
than the wall-clock time it happened at.

That field is the stream's and not the caller's, and ``record()`` refuses to
let anything overwrite it.  Overlap is computed by holding one record's
timestamp against another's, so a record whose ``seconds`` meant something
else would not fail -- it would quietly give a wrong answer.
"""

import json
import os
import time
from typing import Any, Dict, Optional, TextIO


class EventStream:
    """
    Somewhere to write what the scheduler decided.

    Attributes
    ----------
    path : str or None
        The file being written, or ``None`` where nothing is recorded.
    """

    def __init__(self, path: Optional[str] = None):
        """
        Parameters
        ----------
        path : str, optional
            The file to append records to.  A stream with no path discards
            them, which is what a test or a dry run wants.
        """
        self.path = path
        self._start = time.time()
        self._handle: Optional[TextIO] = None
        if path is not None:
            os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
            self._handle = open(path, 'a')

    def record(self, event: str, **fields: Any) -> Dict[str, Any]:
        """
        Write one record.

        Parameters
        ----------
        event : str
            What happened, such as ``'step_started'``

        **fields
            Whatever else is worth knowing about it

        Returns
        -------
        record : dict
            What was written, which is what the tests read

        Raises
        ------
        ValueError
            If a caller tries to supply ``seconds``.  When a record's
            timestamp can be overwritten, two records can carry the same
            field meaning different things, and nothing downstream can tell
            which is which.  That is not hypothetical: a finish record once
            carried a step's *duration* under this name, which silently
            turned every overlap computed from the stream into nonsense.
        """
        if 'seconds' in fields:
            raise ValueError(
                f"A record's 'seconds' is when it happened, measured from "
                f'the start of the run, and belongs to the stream rather '
                f'than to the caller. Record {event!r} tried to supply its '
                f'own. A duration or any other span needs its own name.'
            )
        record: Dict[str, Any] = {
            'event': event,
            'seconds': round(time.time() - self._start, 3),
        }
        record.update(fields)
        if self._handle is not None:
            self._handle.write(json.dumps(record) + '\n')
            # a run that ends badly is exactly the run whose records matter,
            # so nothing is left in a buffer
            self._handle.flush()
        return record

    def close(self) -> None:
        """Stop writing."""
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    def __enter__(self) -> 'EventStream':
        return self

    def __exit__(self, *args) -> None:
        self.close()


def read_events(path: str):
    """
    Read back what a run recorded.

    Parameters
    ----------
    path : str
        The file to read

    Returns
    -------
    events : list of dict
        The records, in the order they were written
    """
    events = []
    with open(path) as handle:
        for line in handle:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events
