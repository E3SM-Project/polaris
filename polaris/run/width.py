"""
How wide a step runs when steps share an allocation.

A step starts once its own width -- the geometric mean of its target and its
minimum -- is free, and it is given everything free up to its target.  On an
idle allocation a step grows to its target.  On a busy one it starts at its
width rather than waiting for its target to come free, and it never starts
at its minimum and crawls.  The width is also what setup sized the job by,
so the widest step always fits.

What a step is given therefore depends on what else is running when it
starts.  That is safe for model steps, whose results are tested to be
bit-for-bit identical across task counts, and it is what lets a step use
cores that would otherwise sit idle.

A step's resources are decided again in its own process, against the part
of the allocation it was placed on, so what is decided here is the size of
that part.
"""

from typing import Dict, Optional

import numpy as np

from polaris.run.pool import Reservation, ResourcePool

# what constrain_resources() may change on a step, which is what has to be
# put back before the step is sized again
_RESIZED = (
    'ntasks',
    'min_tasks',
    'cpus_per_task',
    '_cores',
    '_gpus',
    '_min_gpus',
    'memory_budget',
)


class StepWidths:
    """
    The cores each step may start on, between its width and its target.
    """

    def __init__(self):
        self._floors: Dict[str, int] = {}
        self._ceilings: Dict[str, dict] = {}
        self._available: Optional[dict] = None

    def record_widths(self, steps) -> None:
        """
        Record each step's width, before anything sizes it.

        Parameters
        ----------
        steps : iterable of polaris.Step
            The steps that will run, with the resources they declared
        """
        for step in steps:
            width = np.ceil(np.sqrt(step.cores * step.min_cores))
            self._floors[step.path] = int(width)

    def record_targets(self, steps, available) -> None:
        """
        Record each step's resources once sized against the whole
        allocation, which is the most it may be given.

        Parameters
        ----------
        steps : iterable of polaris.Step
            The steps that will run, sized against ``available``

        available : dict
            The resource view of the whole allocation
        """
        self._available = available
        for step in steps:
            if step.path in self._floors:
                self._ceilings[step.path] = _snapshot(step)

    def reserve(self, pool: ResourcePool, step) -> Optional[Reservation]:
        """
        Give a step as much as is free up to its target, if that is at
        least its width.

        Parameters
        ----------
        pool : polaris.run.pool.ResourcePool
            What is free

        step : polaris.Step
            The step to try to start

        Returns
        -------
        reservation : polaris.run.pool.Reservation or None
            What it was given, sized to match, or ``None`` if its width is
            not free yet
        """
        ceiling = self._ceilings.get(step.path)
        if ceiling is None:
            return pool.reserve(step)

        _restore(step, ceiling)
        target = step.cores
        floor = min(self._floors[step.path], target)
        if floor >= target:
            return pool.reserve(step)

        highest = min(target, pool.free_cores(step.may_span_nodes))
        if highest < floor:
            return None

        # the most that fits is usually all that is free, so that is tried
        # first; otherwise the nodes' shapes or memory decide, and the
        # largest size between the width and that which fits is searched for
        if self._resize(step, ceiling, highest) and pool.fits(step):
            return pool.reserve(step)
        best = None
        low, high = floor, highest - 1
        while low <= high:
            middle = (low + high) // 2
            if self._resize(step, ceiling, middle) and pool.fits(step):
                best = middle
                low = middle + 1
            else:
                high = middle - 1
        if best is None:
            _restore(step, ceiling)
            return None
        self._resize(step, ceiling, best)
        return pool.reserve(step)

    def _resize(self, step, ceiling, cores) -> bool:
        """Size a step to at most ``cores``, or say that it cannot be."""
        _restore(step, ceiling)
        assert self._available is not None
        available = dict(self._available, cores=cores)
        target_cores = step.cores
        target_gpus = step.gpus or 0
        if target_gpus > 0:
            # GPUs shrink with the cores, in the proportion the step has
            gpus = int(np.ceil(cores * target_gpus / target_cores))
            available['gpus'] = max(gpus, step.min_gpus or 0)
        try:
            step.constrain_resources(available)
        except ValueError:
            return False
        return True


def _snapshot(step) -> dict:
    return {name: step.__dict__.get(name) for name in _RESIZED}


def _restore(step, snapshot) -> None:
    step.__dict__.update(snapshot)
