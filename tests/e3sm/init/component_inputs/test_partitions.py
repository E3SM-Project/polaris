import logging
import os

import numpy as np
import pytest

from polaris.tasks.e3sm.init import e3sm_init
from polaris.tasks.e3sm.init.component_inputs.partitions import (
    GPMETIS_LOG,
    RegionGraph,
    build_partitions,
    get_region_graph,
    read_graph_cell_count,
    write_graph,
)
from polaris.tasks.e3sm.init.component_inputs.steps import (
    get_component_inputs_steps,
)
from polaris.tasks.mesh import mesh as mesh_component
from polaris.tasks.ocean import ocean

MESH_NAME = 'u-oi30-lr10'

BASENAME = 'mpas.graph.info'

LOGGER = logging.getLogger('test_partitions')


def test_a_region_graph_keeps_only_the_edges_inside_it():
    """
    Three cells cut from a loop of six are a line, not a loop: the edges to
    the cells outside go with them.
    """
    cells_on_cell, n_edges_on_cell = _ring(6)
    in_region = np.array([True, True, True, False, False, False])

    cells, xadj, adjncy = get_region_graph(
        cells_on_cell, n_edges_on_cell, in_region
    )

    np.testing.assert_array_equal(cells, [0, 1, 2])
    np.testing.assert_array_equal(xadj, [0, 1, 3, 4])
    np.testing.assert_array_equal(adjncy, [1, 0, 2, 1])


def test_a_region_graph_numbers_cells_within_the_region():
    """
    The graph's vertices are the region's cells in mesh order, so a vertex
    number is a position in ``cells``, not an index in the mesh.
    """
    cells_on_cell, n_edges_on_cell = _ring(6)
    in_region = np.array([False, False, False, True, True, True])

    cells, xadj, adjncy = get_region_graph(
        cells_on_cell, n_edges_on_cell, in_region
    )

    np.testing.assert_array_equal(cells, [3, 4, 5])
    np.testing.assert_array_equal(xadj, [0, 1, 3, 4])
    np.testing.assert_array_equal(adjncy, [1, 0, 2, 1])


def test_a_region_graph_ignores_missing_and_unused_neighbors():
    """
    A 0 is a neighbor that is not there, and a slot past ``nEdgesOnCell`` is
    not a neighbor at all, even when it holds a cell index.
    """
    cells_on_cell, n_edges_on_cell = _grid(3, 3)

    _, xadj, adjncy = get_region_graph(
        cells_on_cell, n_edges_on_cell, np.ones(9, dtype=bool)
    )

    # 4 corners with 2 neighbors, 4 edge cells with 3, the center with 4
    np.testing.assert_array_equal(np.diff(xadj), [2, 3, 2, 3, 4, 3, 2, 3, 2])
    assert len(adjncy) == 2 * 12


def test_every_edge_of_a_region_graph_appears_from_both_ends():
    """
    gpmetis requires it, and a region cut at random is where a one-sided
    filter on neighbors would break it.
    """
    cells_on_cell, n_edges_on_cell = _grid(12, 10)
    in_region = np.random.default_rng(seed=0).random(120) < 0.6

    _, xadj, adjncy = get_region_graph(
        cells_on_cell, n_edges_on_cell, in_region
    )

    vertex = np.repeat(np.arange(len(xadj) - 1), np.diff(xadj))
    edges = set(zip(vertex.tolist(), adjncy.tolist(), strict=True))
    assert edges == {(b, a) for a, b in edges}


def test_a_written_graph_has_the_header_gpmetis_expects(tmp_path):
    """
    The vertex count, then the edge count with each edge counted once, then
    one line per vertex of one-based neighbors.
    """
    cells_on_cell, n_edges_on_cell = _ring(4)
    _, xadj, adjncy = get_region_graph(
        cells_on_cell, n_edges_on_cell, np.ones(4, dtype=bool)
    )

    filename = str(tmp_path / 'graph.info')
    write_graph(filename, xadj, adjncy)

    with open(filename) as graph_file:
        lines = graph_file.read().splitlines()
    assert lines == ['4 4', '4 2', '1 3', '2 4', '3 1']
    assert read_graph_cell_count(filename) == 4


def test_each_partition_has_one_line_per_cell_and_every_piece(tmp_path):
    """
    The line count is what the resume logic trusts, and a piece with no
    cells would be a core with nothing to do.
    """
    graph = _write_grid_graph(tmp_path, 20, 20)
    _build(tmp_path, [RegionGraph(filename=graph)], [2, 4, 8], ncells=400)

    for ncores in [2, 4, 8]:
        partition = _read_partition(tmp_path / f'{BASENAME}.part.{ncores}')
        assert len(partition) == 400
        assert set(partition.tolist()) == set(range(ncores))


def test_the_one_piece_partition_is_written_empty(tmp_path):
    """
    gpmetis will not make one, and MPAS reads an empty file as every cell on
    one task.
    """
    graph = _write_grid_graph(tmp_path, 4, 4)
    _build(tmp_path, [RegionGraph(filename=graph)], [1, 2], ncells=16)

    assert (tmp_path / f'{BASENAME}.part.1').read_text() == ''
    assert len(_read_partition(tmp_path / f'{BASENAME}.part.2')) == 16


def test_every_core_gets_a_piece_of_every_region(tmp_path):
    """
    The point of the sea-ice regions: a core that held only open ocean would
    sit idle while the cores with the ice did the work.
    """
    cells_on_cell, n_edges_on_cell = _grid(20, 20)
    polar = np.arange(400) < 120
    regions = []
    for index, in_region in enumerate([polar, ~polar]):
        cells, xadj, adjncy = get_region_graph(
            cells_on_cell, n_edges_on_cell, in_region
        )
        filename = f'region_{index}.graph.info'
        write_graph(str(tmp_path / filename), xadj, adjncy)
        regions.append(RegionGraph(filename=filename, cells=cells))

    _build(tmp_path, regions, [3, 6], ncells=400)

    for ncores in [3, 6]:
        partition = _read_partition(tmp_path / f'{BASENAME}.part.{ncores}')
        assert set(partition[polar].tolist()) == set(range(ncores))
        assert set(partition[~polar].tolist()) == set(range(ncores))


def test_building_in_parallel_gives_the_same_partitions(tmp_path):
    """
    Running several gpmetis processes at once must change only how long the
    step takes.
    """
    for process_count in [1, 3]:
        run_dir = tmp_path / f'{process_count}'
        run_dir.mkdir()
        graph = _write_grid_graph(run_dir, 16, 16)
        _build(
            run_dir,
            [RegionGraph(filename=graph)],
            [2, 4, 8, 16],
            ncells=256,
            process_count=process_count,
        )

    for ncores in [2, 4, 8, 16]:
        name = f'{BASENAME}.part.{ncores}'
        serial = (tmp_path / '1' / name).read_text()
        assert (tmp_path / '3' / name).read_text() == serial


def test_only_the_partitions_and_the_gpmetis_log_are_left(tmp_path):
    """
    The per-region partitions and the files written before being renamed
    are working files.  Anything matching ``<basename>.part.*`` would be
    staged as a partition.
    """
    graph = _write_grid_graph(tmp_path, 8, 8)
    before = set(os.listdir(tmp_path))

    _build(tmp_path, [RegionGraph(filename=graph)], [2, 4], ncells=64)

    assert set(os.listdir(tmp_path)) - before == {
        f'{BASENAME}.part.2',
        f'{BASENAME}.part.4',
        GPMETIS_LOG,
    }
    gpmetis_log = (tmp_path / GPMETIS_LOG).read_text()
    for ncores in [2, 4]:
        assert f'$ gpmetis {graph} {ncores}\n' in gpmetis_log


def test_a_gpmetis_failure_stops_the_step(tmp_path):
    """
    With the error from gpmetis in the message, rather than a partition
    file missing later with no reason given.
    """
    (tmp_path / 'graph.info').write_text('3 2\n2\n1 3\n')

    with pytest.raises(RuntimeError, match='graph.info into 2 pieces'):
        _build(tmp_path, [RegionGraph(filename='graph.info')], [2], ncells=3)
    assert not (tmp_path / f'{BASENAME}.part.2').exists()


def test_a_stale_gpmetis_output_is_not_taken_for_a_new_one(
    tmp_path, monkeypatch
):
    """
    A killed run can leave gpmetis' own output behind.  If the next gpmetis
    writes nothing yet exits cleanly, the old file must not be read in its
    place.
    """
    _fake_gpmetis(tmp_path, monkeypatch, 'exit 0')
    graph = _write_grid_graph(tmp_path, 2, 2)
    (tmp_path / f'{graph}.part.2').write_text('0\n1\n1\n0\n')

    with pytest.raises(RuntimeError, match='into 2 pieces'):
        _build(
            tmp_path,
            [RegionGraph(filename=graph)],
            [2],
            ncells=4,
            process_count=1,
        )
    assert not (tmp_path / f'{BASENAME}.part.2').exists()


def test_a_32_bit_gpmetis_is_named_when_it_fails(tmp_path, monkeypatch):
    """
    The 32-bit build fails on the largest meshes, and the fix -- the Spack
    build the load script provides -- is not something its error says.
    """
    _fake_gpmetis(
        tmp_path,
        monkeypatch,
        'echo " size of idx_t: 32bits, real_t: 32bits"\nexit 1',
    )
    graph = _write_grid_graph(tmp_path, 2, 2)

    with pytest.raises(RuntimeError, match='32-bit build'):
        _build(
            tmp_path,
            [RegionGraph(filename=graph)],
            [2],
            ncells=4,
            process_count=1,
        )


@pytest.mark.parametrize(
    'step_name', ['ocean_graph_partition', 'seaice_graph_partition']
)
def test_the_partition_steps_take_their_cores_from_the_config(step_name):
    """
    And no more than a node has, since the processes share one.
    """
    step, config = _partition_step(step_name)
    config.set('component_inputs', 'partition_cpus_per_task', '8')
    step.constrain_resources(_available(cores=64))
    assert step.cpus_per_task == 8

    config.set('component_inputs', 'partition_cpus_per_task', '128')
    step.constrain_resources(_available(cores=64))
    assert step.cpus_per_task == 64


@pytest.mark.parametrize(
    'step_name', ['ocean_graph_partition', 'seaice_graph_partition']
)
def test_a_login_node_gets_only_its_login_cores(step_name):
    """
    Every partition is still built there, just a few at a time.
    """
    step, _ = _partition_step(step_name)
    step.constrain_resources(_available(cores=4, mpi_allowed=False))
    assert step.cpus_per_task == 4


def _grid(nx, ny):
    """
    A rectangular mesh of square cells, as ``cellsOnCell`` and
    ``nEdgesOnCell``.

    Neighbors off the edge of the grid are 0, as in a culled MPAS mesh, and
    the slots past ``nEdgesOnCell`` hold a real cell index, so that a graph
    that read either would come out wrong rather than by luck right.
    """
    ncells = nx * ny
    index = np.arange(ncells).reshape(ny, nx)
    cells_on_cell = np.ones((ncells, 6), dtype=np.int32)
    for column, (dy, dx) in enumerate([(0, 1), (1, 0), (0, -1), (-1, 0)]):
        y, x = np.divmod(np.arange(ncells), nx)
        y, x = y + dy, x + dx
        inside = (x >= 0) & (x < nx) & (y >= 0) & (y < ny)
        neighbor = np.zeros(ncells, dtype=np.int32)
        neighbor[inside] = index[y[inside], x[inside]] + 1
        cells_on_cell[:, column] = neighbor
    n_edges_on_cell = np.full(ncells, 4, dtype=np.int32)
    return cells_on_cell, n_edges_on_cell


def _ring(ncells):
    """
    Cells in a loop, each with the one before and the one after it.
    """
    cell = np.arange(ncells)
    cells_on_cell = np.zeros((ncells, 3), dtype=np.int32)
    cells_on_cell[:, 0] = (cell - 1) % ncells + 1
    cells_on_cell[:, 1] = (cell + 1) % ncells + 1
    return cells_on_cell, np.full(ncells, 2, dtype=np.int32)


def _write_grid_graph(tmp_path, nx, ny, filename='graph.info'):
    cells_on_cell, n_edges_on_cell = _grid(nx, ny)
    _, xadj, adjncy = get_region_graph(
        cells_on_cell, n_edges_on_cell, np.ones(nx * ny, dtype=bool)
    )
    write_graph(str(tmp_path / filename), xadj, adjncy)
    return filename


def _read_partition(path):
    return np.loadtxt(path, dtype=int, ndmin=1)


def _build(run_dir, regions, cores, ncells, process_count=2):
    cwd = os.getcwd()
    try:
        os.chdir(run_dir)
        build_partitions(
            regions=regions,
            cores=cores,
            basename=BASENAME,
            ncells=ncells,
            process_count=process_count,
            logger=LOGGER,
        )
    finally:
        os.chdir(cwd)


def _fake_gpmetis(tmp_path, monkeypatch, body):
    """
    Put a ``gpmetis`` that runs ``body`` first on the path.  Only a serial
    build sees it: a worker process may come from a forkserver started
    before the path changed.
    """
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    gpmetis = bin_dir / 'gpmetis'
    gpmetis.write_text(f'#!/bin/sh\n{body}\n')
    gpmetis.chmod(0o755)
    monkeypatch.setenv('PATH', f'{bin_dir}{os.pathsep}{os.environ["PATH"]}')


def _partition_step(step_name):
    _reset_shared_components()
    steps, config = get_component_inputs_steps(mesh_name=MESH_NAME)
    step = steps[step_name]
    step.config = config
    return step, config


def _available(cores, mpi_allowed=True):
    return dict(
        cores=cores,
        nodes=1,
        cores_per_node=cores,
        gpus=0,
        gpus_per_node=0,
        memory=None,
        memory_per_node=None,
        mpi_allowed=mpi_allowed,
    )


def _reset_shared_components():
    for component in [e3sm_init, mesh_component, ocean]:
        component.tasks.clear()
        component.steps.clear()
        component.configs.clear()
