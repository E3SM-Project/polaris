import pytest

from polaris.e3sm.init.partitions import get_core_list
from polaris.tasks.e3sm.init.misomip.layout import (
    TaskBounds,
    get_layout,
    get_layout_lines,
    get_task_bounds,
)

# the ocean's cells per task: goal, minimum and maximum
OCEAN = (100.0, 40.0, 2000.0)

# the cells of the ocean meshes at 8, 4 and 2 km, and of MALI's mesh
CELLS = {'o8km': 689, 'o4km': 2759, 'o2km': 11039, 'li1km': 62035}


def _partitions(ocean_cells):
    """
    The task counts both meshes are partitioned for, with the config
    options' bounds
    """
    ocean = get_core_list(ocean_cells, 2000, 40)
    landice = get_core_list(CELLS['li1km'], 30000, 100)
    return sorted(set(int(count) for count in ocean) & set(landice))


def _layout(ocean_cells, tasks_per_node, batch=True):
    bounds = get_task_bounds(ocean_cells, *OCEAN)
    return get_layout(
        [bounds], tasks_per_node, batch, _partitions(ocean_cells)
    )


def test_task_bounds():
    bounds = get_task_bounds(CELLS['o4km'], *OCEAN)
    assert bounds == TaskBounds(target=28, min_tasks=2, max_tasks=68)


def test_a_batch_system_fills_a_node():
    # 28 tasks would leave a node 36 idle cores that still speed the run
    layout = _layout(CELLS['o4km'], 64)
    assert (layout.tasks, layout.nodes, layout.idle_cores) == (64, 1, 0)
    # a target of 110 rounds to 2 nodes
    layout = _layout(CELLS['o2km'], 64)
    assert (layout.tasks, layout.nodes, layout.idle_cores) == (128, 2, 0)


def test_a_batch_system_stops_at_the_most_tasks():
    # 8 km allows at most 17 tasks, and is partitioned for 16 of them
    layout = _layout(CELLS['o8km'], 64)
    assert (layout.tasks, layout.nodes, layout.idle_cores) == (16, 1, 48)
    # 4 km allows at most 68 tasks on a node of 128
    layout = _layout(CELLS['o4km'], 128)
    assert (layout.tasks, layout.nodes, layout.idle_cores) == (64, 1, 64)


def test_a_batch_system_rounds_to_whole_nodes():
    bounds = TaskBounds(target=200, min_tasks=10, max_tasks=1000)
    layout = get_layout([bounds], 64, True, list(range(1, 1001)))
    assert (layout.tasks, layout.nodes) == (192, 3)


def test_a_batch_system_reaches_the_fewest_tasks():
    bounds = TaskBounds(target=10, min_tasks=100, max_tasks=1000)
    layout = get_layout([bounds], 64, True, list(range(1, 1001)))
    assert (layout.tasks, layout.nodes) == (128, 2)


def test_a_single_node_runs_the_target():
    layout = _layout(CELLS['o4km'], 32, batch=False)
    assert (layout.tasks, layout.nodes, layout.idle_cores) == (28, 1, 4)
    layout = _layout(CELLS['o4km'], 8, batch=False)
    assert (layout.tasks, layout.nodes) == (8, 1)


def test_a_single_node_too_small_is_an_error():
    bounds = TaskBounds(target=28, min_tasks=6, max_tasks=68)
    with pytest.raises(ValueError, match='single node of 4 tasks'):
        get_layout([bounds], 4, False, list(range(1, 69)))


def test_the_partitions_set_the_count():
    bounds = TaskBounds(target=28, min_tasks=2, max_tasks=68)
    layout = get_layout([bounds], 64, True, [2, 4, 8, 48])
    assert (layout.tasks, layout.nodes, layout.idle_cores) == (48, 1, 16)
    with pytest.raises(ValueError, match='between 2 and 64'):
        get_layout([bounds], 64, True, [1, 72])


def test_the_most_restrictive_bounds_apply():
    ocean = TaskBounds(target=55, min_tasks=6, max_tasks=275)
    landice = TaskBounds(target=40, min_tasks=12, max_tasks=100)
    layout = get_layout([ocean, landice], 64, True, list(range(1, 300)))
    assert layout.bounds == TaskBounds(target=40, min_tasks=12, max_tasks=100)
    assert (layout.tasks, layout.nodes) == (64, 1)


def test_bounds_that_cross_are_an_error():
    ocean = TaskBounds(target=28, min_tasks=2, max_tasks=10)
    landice = TaskBounds(target=40, min_tasks=12, max_tasks=100)
    with pytest.raises(ValueError, match='at least 12 tasks but allow'):
        get_layout([ocean, landice], 64, True, list(range(1, 300)))


def test_layout_lines():
    layout = _layout(CELLS['o8km'], 64)
    lines = get_layout_lines(layout, {'the ocean': OCEAN}, 'chrysalis')
    assert lines == [
        'the ocean: a goal of 100 cells per task, with at least 40 and at '
        'most 2000',
        'tasks: a target of 7, with at least 1 and at most 17',
        'machine: chrysalis, a batch system of 64 tasks per node',
        'layout: 16 tasks on 1 node, 48 cores idle',
    ]
    lines = get_layout_lines(layout, {'the ocean': OCEAN}, '')
    assert lines[2] == 'machine: a batch system of 64 tasks per node'


def test_layout_lines_without_a_goal():
    layout = _layout(CELLS['o8km'], 64)
    lines = get_layout_lines(
        layout, {'the ocean': OCEAN, 'MALI': (None, 100.0, 30000.0)}, ''
    )
    assert lines[1] == (
        'MALI: no goal yet, with at least 100 and at most 30000 cells per task'
    )
