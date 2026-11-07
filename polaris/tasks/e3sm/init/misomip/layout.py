"""
The task count of a MISOMIP E3SM case, from a goal number of cells per task
and bounds on it, and from the machine Polaris runs on
"""

import math
from dataclasses import dataclass


@dataclass
class TaskBounds:
    """
    The tasks a model's mesh calls for

    Attributes
    ----------
    target : int
        The tasks that give the goal number of cells per task

    min_tasks : int
        The fewest tasks, with at most the maximum cells per task

    max_tasks : int
        The most tasks, with at least the minimum cells per task
    """

    target: int
    min_tasks: int
    max_tasks: int


@dataclass
class Layout:
    """
    A case's task count and the bounds and machine facts it comes from

    Attributes
    ----------
    bounds : polaris.tasks.e3sm.init.misomip.layout.TaskBounds
        The most restrictive of the models' bounds

    tasks_per_node : int
        The machine's cores per node, or its MPI tasks per node if fewer

    batch : bool
        Whether the machine has a batch system, rather than a single node

    nodes : int
        The nodes the tasks run on

    tasks : int
        The tasks every component runs on
    """

    bounds: TaskBounds
    tasks_per_node: int
    batch: bool
    nodes: int
    tasks: int

    @property
    def idle_cores(self):
        """
        The cores of the case's nodes that run no task
        """
        return self.nodes * self.tasks_per_node - self.tasks


def get_task_bounds(
    cells, goal_cells_per_task, min_cells_per_task, max_cells_per_task
):
    """
    Get the tasks a model's mesh calls for, from cells per task

    Parameters
    ----------
    cells : int
        The cells of the model's mesh

    goal_cells_per_task : float
        The cells per task that sets the target

    min_cells_per_task : float
        The fewest cells per task, which sets the most tasks

    max_cells_per_task : float
        The most cells per task, which sets the fewest tasks

    Returns
    -------
    bounds : polaris.tasks.e3sm.init.misomip.layout.TaskBounds
        The target, fewest and most tasks
    """
    return TaskBounds(
        target=max(1, _round(cells / goal_cells_per_task)),
        min_tasks=max(1, math.ceil(cells / max_cells_per_task)),
        max_tasks=max(1, math.floor(cells / min_cells_per_task)),
    )


def get_layout(model_bounds, tasks_per_node, batch, partitions):
    """
    Get a case's task count.  The most restrictive of the models' bounds
    applies.  On a batch system, the tasks fill whole nodes near the
    target, up to the most tasks; on a single node, they are the target, or
    the node's tasks if fewer.  The count is then the most tasks at or
    below that the meshes are partitioned for.

    Parameters
    ----------
    model_bounds : list of polaris.tasks.e3sm.init.misomip.layout.TaskBounds
        The bounds of each model whose mesh limits the tasks

    tasks_per_node : int
        The machine's cores per node, or its MPI tasks per node if fewer

    batch : bool
        Whether the machine has a batch system, rather than a single node

    partitions : list of int
        The task counts every mesh is partitioned for

    Returns
    -------
    layout : polaris.tasks.e3sm.init.misomip.layout.Layout
        The task count, nodes and what they come from
    """
    bounds = TaskBounds(
        target=min(bound.target for bound in model_bounds),
        min_tasks=max(bound.min_tasks for bound in model_bounds),
        max_tasks=min(bound.max_tasks for bound in model_bounds),
    )
    if bounds.min_tasks > bounds.max_tasks:
        raise ValueError(
            f'The meshes need at least {bounds.min_tasks} tasks but allow at '
            f'most {bounds.max_tasks}.'
        )
    target = min(max(bounds.target, bounds.min_tasks), bounds.max_tasks)
    if batch:
        nodes = max(1, _round(target / tasks_per_node))
        while nodes * tasks_per_node < bounds.min_tasks:
            nodes += 1
        tasks = min(nodes * tasks_per_node, bounds.max_tasks)
    else:
        tasks = min(target, tasks_per_node)
        if tasks < bounds.min_tasks:
            raise ValueError(
                f'The machine is a single node of {tasks_per_node} tasks, '
                f'fewer than the {bounds.min_tasks} the meshes need.'
            )

    covered = [count for count in partitions if count <= tasks]
    if not covered or max(covered) < bounds.min_tasks:
        raise ValueError(
            f'No task count the meshes are partitioned for lies between '
            f'{bounds.min_tasks} and {tasks}.'
        )
    tasks = max(covered)
    nodes = math.ceil(tasks / tasks_per_node)
    return Layout(
        bounds=bounds,
        tasks_per_node=tasks_per_node,
        batch=batch,
        nodes=nodes,
        tasks=tasks,
    )


def get_layout_lines(layout, cells_per_task, machine):
    """
    Get the lines that describe a case's layout and what it comes from

    Parameters
    ----------
    layout : polaris.tasks.e3sm.init.misomip.layout.Layout
        The layout

    cells_per_task : dict of str to tuple of float
        The goal, or ``None`` if there is none yet, minimum and maximum
        cells per task of each model whose
        mesh limits the tasks, keyed by its name

    machine : str
        The machine the layout is for, or an empty string if Polaris has no
        name for it

    Returns
    -------
    lines : list of str
        The description
    """
    lines = []
    for model, (goal, low, high) in cells_per_task.items():
        if goal is None:
            lines.append(
                f'{model}: no goal yet, with at least {low:g} and at most '
                f'{high:g} cells per task'
            )
            continue
        lines.append(
            f'{model}: a goal of {goal:g} cells per task, with at least '
            f'{low:g} and at most {high:g}'
        )
    bounds = layout.bounds
    lines.append(
        f'tasks: a target of {bounds.target}, with at least '
        f'{bounds.min_tasks} and at most {bounds.max_tasks}'
    )
    system = 'a batch system' if layout.batch else 'a single node'
    name = f'{machine}, ' if machine else ''
    lines.append(
        f'machine: {name}{system} of {layout.tasks_per_node} tasks per node'
    )
    nodes = 'node' if layout.nodes == 1 else 'nodes'
    idle = f', {layout.idle_cores} cores idle' if layout.idle_cores else ''
    lines.append(
        f'layout: {layout.tasks} tasks on {layout.nodes} {nodes}{idle}'
    )
    return lines


def _round(value):
    """
    Round a positive value half up
    """
    return math.floor(value + 0.5)
