import logging
import os

import numpy as np
import pytest

from polaris import Component
from polaris.config import PolarisConfigParser
from polaris.e3sm.init.graph_partition import GraphPartitionStep
from polaris.e3sm.init.partitions import (
    GPMETIS_LOG,
    RegionGraph,
    build_partitions,
    get_core_list,
    get_region_graph,
    partitions_to_build,
    read_graph_cell_count,
    write_graph,
)

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


def test_the_cell_count_comes_from_the_graph_header(tmp_path):
    """
    Counting lines instead would include the header and overcount by one.
    """
    graph = tmp_path / 'graph.info'
    graph.write_text('4 5\n2\n1 3\n2 4\n3\n')
    assert read_graph_cell_count(str(graph)) == 4
    assert sum(1 for _ in open(graph)) == 5


def test_the_core_counts_respect_the_bounds():
    cores = get_core_list(
        ncells=1000000, max_cells_per_core=30000, min_cells_per_core=2
    )
    assert cores.min() >= 1000000 // 30000
    assert cores.max() <= 1000000 // 2


def test_a_small_mesh_can_run_on_one_core():
    """
    A mesh with fewer cells than one core's worth is allowed a single
    partition; a larger one is not, since it would be a pointless file.
    """
    assert 1 in get_core_list(ncells=1000, max_cells_per_core=30000)
    assert 1 not in get_core_list(ncells=100000, max_cells_per_core=30000)


def test_the_core_counts_are_sorted_and_unique():
    cores = get_core_list(ncells=500000)
    assert list(cores) == sorted(set(cores.tolist()))


def test_awkward_core_counts_are_left_out():
    """
    The list keeps counts that factor well for a decomposition.  A prime like
    101 is not one, and is not a node size either.
    """
    cores = get_core_list(
        ncells=1000000, max_cells_per_core=30000, min_cells_per_core=2
    )
    assert 101 not in cores
    assert 128 in cores


def test_whole_node_counts_survive_even_when_they_factor_badly():
    """
    Node sizes are added regardless of the factor rule, because a run is laid
    out in nodes.  44 is 2*2*11 and 52 is 2*2*13; both have a prime factor
    above 7, so the factor rule rejects them on their own merits.
    """
    cores = get_core_list(
        ncells=1000000, max_cells_per_core=30000, min_cells_per_core=2
    )
    for node_size in [44, 52, 112, 256]:
        assert node_size in cores, node_size


def test_a_node_size_below_the_lower_bound_is_still_left_out():
    """
    Being a node size does not override the bounds: a partition that small
    would put more cells on a core than asked for.
    """
    cores = get_core_list(
        ncells=1000000, max_cells_per_core=30000, min_cells_per_core=2
    )
    # 1000000 / 30000 rounds down to a lower bound of 33, so 30 is too few.
    # The smallest count kept is 36 rather than 33, since 33 is 3*11 and
    # neither factors well nor is a node size.
    assert cores.min() >= 33
    assert 30 not in cores
    # with a smaller mesh the same node size is in range, and kept
    assert 30 in get_core_list(ncells=500000, max_cells_per_core=30000)


def test_the_core_counts_never_exceed_the_cell_count():
    """
    The step raises on this, so the list must not produce it for a mesh as
    small as the ones we test on.
    """
    for ncells in [1000, 7313, 100000]:
        cores = get_core_list(ncells=ncells)
        assert cores.max() <= ncells, ncells


def test_the_core_counts_are_plain_integers():
    cores = get_core_list(ncells=7313)
    assert np.issubdtype(cores.dtype, np.integer)


def _write_partition(tmp_path, ncores, nlines):
    path = tmp_path / f'graph.info.part.{ncores}'
    path.write_text('1\n' * nlines)
    return path


def test_a_finished_partition_is_not_rebuilt(tmp_path):
    """
    Resuming is the whole point: a day of gpmetis must not be repeated because
    a job hit its walltime.
    """
    ncells = 100
    _write_partition(tmp_path, 4, ncells)
    _write_partition(tmp_path, 8, ncells)

    remaining = partitions_to_build(
        [4, 8, 16], str(tmp_path / 'graph.info'), ncells
    )
    assert remaining == [16]


def test_a_truncated_partition_is_rebuilt(tmp_path):
    """
    A job killed mid-write leaves a partition covering part of the mesh.  It
    exists, so an existence check would skip it and hand E3SM a broken file.
    """
    ncells = 100
    _write_partition(tmp_path, 4, ncells)
    _write_partition(tmp_path, 8, ncells // 2)

    remaining = partitions_to_build(
        [4, 8], str(tmp_path / 'graph.info'), ncells
    )
    assert remaining == [8]


def test_the_one_piece_partition_counts_as_finished(tmp_path):
    """
    It is written empty on purpose -- MPAS reads that as every cell on one
    task -- so counting lines would rebuild it forever.
    """
    (tmp_path / 'graph.info.part.1').write_text('')

    remaining = partitions_to_build(
        [1, 4], str(tmp_path / 'graph.info'), ncells=100
    )
    assert remaining == [4]


def test_nothing_to_do_is_an_empty_list(tmp_path):
    """
    Which is what lets a step return before running the tools at all.
    """
    ncells = 100
    for ncores in [4, 8]:
        _write_partition(tmp_path, ncores, ncells)

    assert (
        partitions_to_build([4, 8], str(tmp_path / 'graph.info'), ncells) == []
    )


def test_the_order_asked_for_is_kept(tmp_path):
    """
    The steps log the first and last counts, so the order has to survive.
    """
    remaining = partitions_to_build(
        [16, 4, 8], str(tmp_path / 'graph.info'), ncells=100
    )
    assert remaining == [16, 4, 8]


def test_a_partition_step_reads_the_section_it_is_given():
    """
    So a workflow with two graphs, such as an ocean and a land-ice mesh, can
    give each its own bounds.
    """
    step = _graph_partition_step()
    step.constrain_resources(_available(cores=64))
    assert step.cpus_per_task == 8
    assert step.min_cpus_per_task == 2

    cores = step.get_core_counts(ncells=1000)
    assert cores[0] == 10
    assert cores[-1] <= 1000 // 4


def test_a_partition_step_links_the_graph_it_is_given():
    step = _graph_partition_step()
    (entry,) = step.input_data
    assert entry['filename'] == 'graph.info'
    assert entry['work_dir_target'] == 'landice/mesh/graph.info'


def _graph_partition_step():
    config = PolarisConfigParser()
    config.add_section('landice_inputs')
    for option, value in [
        ('max_cells_per_core', '100'),
        ('min_cells_per_core', '4'),
        ('partition_cpus_per_task', '8'),
        ('partition_min_cpus_per_task', '2'),
    ]:
        config.set('landice_inputs', option, value)
    step = GraphPartitionStep(
        component=Component(name='landice'),
        name='graph_partition',
        subdir='graph_partition',
        basename='mpasli.graph.info',
        section='landice_inputs',
        graph_target='landice/mesh/graph.info',
    )
    step.config = config
    return step


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
