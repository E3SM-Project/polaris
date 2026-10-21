import os

import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf
from mpas_tools.logging import check_call

from polaris.step import Step
from polaris.tasks.e3sm.init.component_inputs.models import check_seaice_model
from polaris.tasks.e3sm.init.component_inputs.partitions import (
    RegionGraph,
    build_partitions,
    get_core_list,
    get_region_graph,
    partitions_to_build,
    write_graph,
)
from polaris.tasks.e3sm.init.component_inputs.seaice_partition_map import (
    CLIMATOLOGY_FILENAME,
)

#: The base name the partition files carry.  As with the ocean partitions,
#: the creation date is added when the files are staged, not here.
GRAPH_BASENAME = 'mpas-seaice.graph.info'

#: The name the mapping-file step is registered under as a dependency.
MAP_DEPENDENCY = 'seaice_partition_map'

#: The mask of where ice is present in the QU60km climatology.  The
#: climatology itself comes from
#: :py:mod:`polaris.tasks.e3sm.init.component_inputs.seaice_partition_map`,
#: which also names it.
ICE_PRESENT_FILENAME = 'icePresent_QU60km_polar.nc'

#: The region of each cell, which ``prepare_seaice_partitions`` writes.
REGIONS_FILENAME = 'regions.nc'

#: Every partition, for plotting with the mesh, if
#: ``[component_inputs] plot_seaice_partitions`` asks for it.
PLOT_FILENAME = 'partition_diag.nc'


class SeaiceGraphPartitionStep(Step):
    """
    A step for partitioning the sea-ice mesh.

    Sea-ice partitions are not ocean partitions with a different name.  They
    are weighted by where sea ice actually occurs, so that the cost of the ice
    physics is spread evenly rather than the cell count -- which is why this
    needs a QU60km climatology and a mapping file, and the ocean partitioning
    needs neither.

    The weights come from
    :py:class:`~polaris.tasks.e3sm.init.component_inputs.seaice_partition_map.SeaicePartitionMapStep`
    rather than being built here, so that this step needs no MPI.

    The partitions themselves follow MPAS-Tools' ``create_seaice_partitions``:
    each region of the mesh is partitioned on its own, and every core gets a
    piece of every region.  The tool is not called, though.  It gets each
    region's graph by culling a copy of the mesh with ``MpasCellCuller.x``,
    which took over two hours on the finest mesh, when the same graph follows
    from ``cellsOnCell`` in seconds.  It also builds one partition at a time.

    The mesh being partitioned is
    :py:class:`~polaris.tasks.e3sm.init.component_inputs.seaice_mesh.SeaiceMeshStep`'s
    output.  Compass partitioned an ocean restart instead, which is the
    coupling D7 removes; it also had to drop ``cullCell`` from that file
    first, and the culled mesh this reads never had one.

    As with the ocean partitions, the core counts follow from a cell count
    that is not known until the mesh exists, so the partition files cannot be
    declared as outputs at setup.

    Attributes
    ----------
    seaice_mesh_step : polaris.Step
        The step that wrote ``seaice_mesh.nc``.
    """

    def __init__(
        self,
        component,
        subdir,
        seaice_mesh_step,
        partition_map_step,
        name='seaice_graph_partition',
    ):
        """
        Create a new step.

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to.

        subdir : str
            The subdirectory for the step.

        seaice_mesh_step : polaris.Step
            The step that wrote ``seaice_mesh.nc``.

        partition_map_step : polaris.Step
            The step that built the QU60km-to-mesh mapping file.

        name : str, optional
            The name of the step.
        """
        super().__init__(component=component, name=name, subdir=subdir)
        self.seaice_mesh_step = seaice_mesh_step

        # the mapping file's path is not known until the step has run, so it
        # comes from the dependency rather than being declared as an input
        self.add_dependency(partition_map_step, name=MAP_DEPENDENCY)

        for filename in (CLIMATOLOGY_FILENAME, ICE_PRESENT_FILENAME):
            self.add_input_file(
                filename=filename,
                target=filename,
                database='partition',
                database_component='seaice',
            )
        self.add_input_file(
            filename='seaice_mesh.nc',
            work_dir_target=os.path.join(
                seaice_mesh_step.path, 'seaice_mesh.nc'
            ),
        )

    def setup(self):
        """
        Refuse a model whose packaging is not supported, before anything runs.
        """
        super().setup()
        check_seaice_model(self.config)
        section = self.config['component_inputs']
        self.cpus_per_task = section.getint('partition_cpus_per_task')
        self.min_cpus_per_task = section.getint('partition_min_cpus_per_task')

    def constrain_resources(self, available_resources):
        """
        Take the number of partitions to build at once from the config.

        Parameters
        ----------
        available_resources : dict
            The resources available to the step.
        """
        section = self.config['component_inputs']
        self.cpus_per_task = section.getint('partition_cpus_per_task')
        self.min_cpus_per_task = section.getint('partition_min_cpus_per_task')
        super().constrain_resources(available_resources)

    def run(self):
        """
        Weight the mesh by the sea-ice climatology, then partition it.
        """
        check_seaice_model(self.config)
        config = self.config
        logger = self.logger

        section = config['component_inputs']
        cores, ncells = self._core_counts()
        remaining = partitions_to_build(cores, GRAPH_BASENAME, ncells)
        done = len(cores) - len(remaining)
        logger.info(
            f'Partitioning into {cores[0]} to {cores[-1]} pieces: '
            f'{len(remaining)} to build, {self.cpus_per_task} at a time'
            + (f', {done} already complete' if done else '')
        )
        if not remaining:
            logger.info('Every partition is already built.')
            return

        # the mapping file (and the path it was written to) comes from the
        # step that built it
        remapper = self.dependencies[MAP_DEPENDENCY].remapper

        check_call(
            [
                'prepare_seaice_partitions',
                '-i',
                CLIMATOLOGY_FILENAME,
                '-p',
                ICE_PRESENT_FILENAME,
                '-m',
                'seaice_mesh.nc',
                '-o',
                '.',
                '-w',
                remapper.map_filename,
            ],
            logger,
        )

        build_partitions(
            regions=_write_region_graphs(),
            cores=remaining,
            basename=GRAPH_BASENAME,
            ncells=ncells,
            process_count=self.cpus_per_task,
            logger=logger,
        )

        if section.getboolean('plot_seaice_partitions'):
            _write_partition_diagnostics(cores, ncells)

    def _core_counts(self):
        """
        The core counts to partition into, and the cell count they came from.

        The cell count is returned too because the caller needs it to tell a
        finished partition file from one an interrupted job left part-written.
        """
        with xr.open_dataset('seaice_mesh.nc') as ds_mesh:
            ncells = int(ds_mesh.sizes['nCells'])

        section = self.config['component_inputs']
        cores = get_core_list(
            ncells=ncells,
            max_cells_per_core=section.getint('max_cells_per_core'),
            min_cells_per_core=section.getint('min_cells_per_core'),
        )
        if cores[-1] > ncells:
            raise ValueError(
                f'Cannot partition {ncells} cells into {cores[-1]} pieces.'
            )
        return list(cores), ncells


def _write_region_graphs():
    """
    Write the graph of each region's cells, and say which cells each covers.
    """
    with xr.open_dataset('seaice_mesh.nc') as ds_mesh:
        cells_on_cell = ds_mesh.cellsOnCell.values
        n_edges_on_cell = ds_mesh.nEdgesOnCell.values
    with xr.open_dataset(REGIONS_FILENAME) as ds_regions:
        region = ds_regions.region.values
        nregions = int(ds_regions.attrs['nRegions'])

    regions = []
    for index in range(nregions):
        in_region = region == index
        if not np.any(in_region):
            # a mesh with no sea ice at all still needs partitions, and they
            # are then just partitions of the other region
            continue
        cells, xadj, adjncy = get_region_graph(
            cells_on_cell, n_edges_on_cell, in_region
        )
        filename = f'seaice_region_{index}.graph.info'
        write_graph(filename, xadj, adjncy)
        regions.append(RegionGraph(filename=filename, cells=cells))
    return regions


def _write_partition_diagnostics(cores, ncells):
    """
    Write every partition into one file, to plot over ``seaice_mesh.nc``.
    """
    ds = xr.Dataset()
    for ncores in cores:
        if ncores == 1:
            # written empty, which MPAS reads as every cell on task 0
            partition = np.zeros(ncells, dtype=np.int32)
        else:
            partition = np.loadtxt(
                f'{GRAPH_BASENAME}.part.{ncores}', dtype=np.int32
            )
        ds[f'partition_{ncores}'] = ('nCells', partition)
    write_netcdf(ds, PLOT_FILENAME)
