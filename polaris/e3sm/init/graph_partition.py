import shutil

from polaris.e3sm.init.partitions import (
    RegionGraph,
    build_partitions,
    get_core_list,
    partitions_to_build,
    read_graph_cell_count,
)
from polaris.step import Step


class GraphPartitionStep(Step):
    """
    A step for partitioning an MPAS graph into the core counts E3SM runs use.

    By default the graph is linked in as ``graph.info`` and ``gpmetis`` is run
    over it once per core count, several at a time.  A subclass that builds
    its own graphs, as sea ice does for its regions, overrides ``run()`` and
    uses :py:meth:`get_core_counts` and :py:attr:`cpus_per_task` from here.

    The core counts depend on the mesh's cell count, which is not known until
    the graph exists, so the partition files cannot be declared as outputs at
    setup.  A step that stages them has to find them at run time.

    The step reads four options from its config section:
    ``max_cells_per_core`` and ``min_cells_per_core`` bound the core counts,
    and ``partition_cpus_per_task`` and ``partition_min_cpus_per_task`` set
    how many partitions are built at once.

    Attributes
    ----------
    basename : str
        The stem of every partition file: ``<basename>.part.<ncores>``.  The
        default ``run()`` also copies the graph to ``<basename>``, so it can
        be staged beside its partitions under the same name.

    section : str
        The config section the step's options are read from.
    """

    def __init__(
        self,
        component,
        name,
        subdir,
        basename,
        section,
        graph_target=None,
    ):
        """
        Create a new step.

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to.

        name : str
            The name of the step.

        subdir : str
            The subdirectory for the step.

        basename : str
            The stem of every partition file.

        section : str
            The config section the step's options are read from.

        graph_target : str, optional
            The path, relative to the base work directory, of the graph to
            partition.  It is linked in as ``graph.info``.  A subclass that
            builds its own graphs leaves this out.
        """
        super().__init__(component=component, name=name, subdir=subdir)
        self.basename = basename
        self.section = section

        if graph_target is not None:
            self.add_input_file(
                filename='graph.info', work_dir_target=graph_target
            )

    def setup(self):
        """
        Take the number of partitions to build at once from the config.
        """
        super().setup()
        self._set_cpus_per_task()

    def constrain_resources(self, available_resources):
        """
        Take the number of partitions to build at once from the config.

        Parameters
        ----------
        available_resources : dict
            The resources available to the step.
        """
        self._set_cpus_per_task()
        super().constrain_resources(available_resources)

    def run(self):
        """
        Partition ``graph.info`` into each core count.
        """
        super().run()
        logger = self.logger

        # the graph is staged beside its partitions, under the name they carry
        shutil.copyfile('graph.info', self.basename)

        ncells = read_graph_cell_count('graph.info')
        cores = self.get_core_counts(ncells)

        remaining = partitions_to_build(cores, self.basename, ncells)
        done = len(cores) - len(remaining)
        logger.info(
            f'Partitioning {ncells} cells into {cores[0]} to '
            f'{cores[-1]} pieces: {len(remaining)} to build, '
            f'{self.cpus_per_task} at a time'
            + (f', {done} already complete' if done else '')
        )

        build_partitions(
            regions=[RegionGraph(filename='graph.info')],
            cores=remaining,
            basename=self.basename,
            ncells=ncells,
            process_count=self.cpus_per_task,
            logger=logger,
        )

    def get_core_counts(self, ncells):
        """
        The core counts to partition a mesh into, from the config's bounds.

        Parameters
        ----------
        ncells : int
            The number of cells in the mesh.

        Returns
        -------
        list of int
            The core counts, in increasing order.

        Raises
        ------
        ValueError
            If the bounds ask for more pieces than there are cells.
        """
        section = self.config[self.section]
        cores = get_core_list(
            ncells=ncells,
            max_cells_per_core=section.getint('max_cells_per_core'),
            min_cells_per_core=section.getint('min_cells_per_core'),
        )
        if cores[-1] > ncells:
            raise ValueError(
                f'Cannot partition {ncells} cells into {cores[-1]} pieces.'
            )
        return list(cores)

    def _set_cpus_per_task(self):
        section = self.config[self.section]
        self.cpus_per_task = section.getint('partition_cpus_per_task')
        self.min_cpus_per_task = section.getint('partition_min_cpus_per_task')
