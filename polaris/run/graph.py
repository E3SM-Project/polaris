"""
The graph of which steps have to run before which.

Edges come from two places, and both are needed.  A step may name another
step as a dependency, which is what
:py:meth:`polaris.Step.add_dependency` is for and is the only way to say
"after that one" when the files involved are not known until run time.  And
a step may consume a file another step produces, which the two of them
declare through ``add_input_file()`` and ``add_output_file()`` without
either naming the other.

The order steps were listed in contributes nothing except as the tie-break
for choosing among steps that could all run.  A suite that relies on listed
order without declaring a real dependency is relying on something the
serial runner happened to give it, and the concurrent path is allowed to
expose that as a failure rather than to preserve it.

The graph is checked before anything runs.  An unsatisfiable input
discovered forty minutes into a suite costs much more than the same error
reported at the start.
"""

import os
from typing import Dict, FrozenSet, Iterable, List, Tuple

from polaris.run.lifecycle import step_is_complete
from polaris.step import Step


class StepNode:
    """
    One step in the graph.

    Attributes
    ----------
    path : str
        The step's path within the base work directory, which is what
        identifies it: a step shared between tasks is one node with one
        path.

    step : polaris.Step
        The step itself.

    requires : frozenset of str
        The paths of the steps that have to succeed before this one may
        start.

    satisfied : bool
        Whether this step has already run or is cached, so that its outputs
        are available and it must not be run again.
    """

    def __init__(self, path, step, requires, satisfied):
        self.path = path
        self.step = step
        self.requires = requires
        self.satisfied = satisfied


class StepGraph:
    """
    Which steps have to run before which.

    Attributes
    ----------
    nodes : dict of polaris.run.graph.StepNode
        The steps, keyed by path, in the order setup listed them.  The
        order is the tie-break for choosing among steps that could all run,
        and it is stable, so two runs of the same work make the same
        choices.
    """

    def __init__(self, nodes: Dict[str, StepNode]):
        self.nodes = nodes
        self._dependents: Dict[str, List[str]] = {path: [] for path in nodes}
        for path, node in nodes.items():
            for required in node.requires:
                self._dependents[required].append(path)

    def dependents(self, path: str) -> Tuple[str, ...]:
        """
        The steps that name this one, directly, among their requirements.

        Parameters
        ----------
        path : str
            The path of the step to ask about

        Returns
        -------
        dependents : tuple of str
            The paths of the steps that require it, in graph order
        """
        return tuple(self._dependents[path])

    def descendants(self, path: str) -> FrozenSet[str]:
        """
        Every step that this one is required by, directly or through others.

        This is what a failure blocks: a step whose requirement failed can
        never run, and neither can anything behind it.

        Parameters
        ----------
        path : str
            The path of the step to ask about

        Returns
        -------
        descendants : frozenset of str
            The paths of every step downstream of it
        """
        found: set = set()
        pending = list(self._dependents[path])
        while pending:
            current = pending.pop()
            if current in found:
                continue
            found.add(current)
            pending.extend(self._dependents[current])
        return frozenset(found)


def build_step_graph(steps: Iterable[Step]) -> StepGraph:
    """
    Build the graph of which steps have to run before which, and check it.

    Parameters
    ----------
    steps : iterable of polaris.Step
        The steps selected to run, in the order setup listed them -- suite,
        then task, then step within a task.  A step shared between tasks
        may appear more than once and becomes one node.

    Returns
    -------
    graph : polaris.run.graph.StepGraph
        The graph, which is valid if this returns at all

    Raises
    ------
    ValueError
        If two steps produce the same file, if a step needs an input that
        nothing produces and that does not already exist, or if the
        requirements form a cycle
    """
    selected = _deduplicate(steps)
    producers = _find_producers(selected)
    requires = {
        path: _requirements_of(step, selected, producers)
        for path, step in selected.items()
    }
    _check_cycles(requires)

    nodes = {
        path: StepNode(
            path=path,
            step=step,
            requires=requires[path],
            satisfied=step.cached or step_is_complete(step),
        )
        for path, step in selected.items()
    }
    return StepGraph(nodes)


def _deduplicate(steps: Iterable[Step]) -> Dict[str, Step]:
    """Reduce the selected steps to one entry per step, in listed order."""
    selected: Dict[str, Step] = {}
    for step in steps:
        if step.path not in selected:
            selected[step.path] = step
    return selected


def _find_producers(selected: Dict[str, Step]) -> Dict[str, str]:
    """
    Map each file a selected step produces to the step that produces it.

    Two steps writing the same file is a race as soon as they can run at
    the same time, and it is rejected here rather than left to whichever
    finishes last.
    """
    producers: Dict[str, str] = {}
    for path, step in selected.items():
        for output in step.outputs:
            filename = _resolve(output)
            if filename in producers and producers[filename] != path:
                raise ValueError(
                    f'Steps {producers[filename]} and {path} both produce '
                    f'{filename}. Two steps writing one file cannot run at '
                    f'the same time.'
                )
            producers[filename] = path
    return producers


def _resolve(filename: str) -> str:
    """
    The path to compare a file by, following any symlinks along the way.

    Setup links a step's inputs into its own work directory, so a step that
    consumes another's output names a link that points there.  Until the
    other step runs, that link dangles: it does not exist, and the file it
    is waiting for has a different path.  Comparing what a link resolves to
    is what connects the two.

    A link that does not exist yet resolves to itself, and a name with no
    links in it is merely normalized, so this is safe to apply to every
    path on both sides of the comparison.
    """
    return os.path.realpath(filename)


def _requirements_of(
    step: Step, selected: Dict[str, Step], producers: Dict[str, str]
) -> FrozenSet[str]:
    """
    Work out what one step has to wait for, and check that it can be met.

    A dependency the step named that was not selected is left alone: it may
    have run in an earlier invocation, and whether its outputs are there is
    the input check's question rather than this one's.
    """
    required = set()

    for dependency in step.dependencies.values():
        if dependency.path in selected and dependency.path != step.path:
            required.add(dependency.path)

    for input_file in step.inputs:
        filename = _resolve(input_file)
        producer = producers.get(filename)
        if producer is not None:
            if producer != step.path:
                required.add(producer)
            continue
        if not os.path.exists(filename):
            raise ValueError(
                f'Step {step.path} needs the input file {input_file}, which '
                f'does not exist and which no step being run produces.'
            )

    return frozenset(required)


def _check_cycles(requires: Dict[str, FrozenSet[str]]) -> None:
    """
    Check that the requirements can be satisfied in some order.

    Kahn's algorithm: repeatedly take the steps nothing is still waiting
    for.  Whatever is left when none remain is a cycle, and naming its
    members is what makes the error usable.
    """
    remaining = {path: set(needed) for path, needed in requires.items()}
    ready = [path for path, needed in remaining.items() if not needed]
    while ready:
        path = ready.pop()
        del remaining[path]
        for other, needed in remaining.items():
            if path not in needed:
                continue
            needed.discard(path)
            if not needed:
                # newly ready, and only now, so nothing is listed twice
                ready.append(other)

    if remaining:
        cycle = ', '.join(sorted(remaining))
        raise ValueError(
            f'These steps depend on each other, directly or through others, '
            f'so none of them can run: {cycle}.'
        )
