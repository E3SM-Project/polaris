import os
import shutil

from polaris import Step
from polaris.tasks.e3sm.init.component_inputs.models import check_ocean_model
from polaris.tasks.e3sm.init.component_inputs.partitions import (
    RegionGraph,
    build_partitions,
    get_core_list,
    partitions_to_build,
    read_graph_cell_count,
)

#: The stem of every partition file this step writes, and the name the graph
#: is staged under beside them.  The creation date is added when the files
#: are staged, not here.
GRAPH_BASENAME = 'mpas-o.graph.info'


class OceanGraphPartitionStep(Step):
    """
    A step for partitioning the ocean graph into the core counts E3SM runs use.

    The graph itself comes from the cull step -- the ``ocean`` prefix, which is
    the domain the ocean initial condition is built on -- so nothing is
    regenerated here; this runs ``gpmetis`` over it once per core count,
    several at a time.

    The core counts depend on the mesh's cell count, which is not known until
    the graph file exists, so the partition files cannot be declared as outputs
    at setup.  The assembly step therefore depends on this step and stages what
    it finds, rather than naming each partition in advance.

    Attributes
    ----------
    cull_mesh_step : polaris.tasks.e3sm.init.topo.cull.CullMeshStep
        The step that wrote the ocean graph.
    """

    def __init__(
        self, component, subdir, cull_mesh_step, name='ocean_graph_partition'
    ):
        """
        Create a new step.

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to.

        subdir : str
            The subdirectory for the step.

        cull_mesh_step : polaris.tasks.e3sm.init.topo.cull.CullMeshStep
            The step that wrote ``culled_ocean_graph.info``.

        name : str, optional
            The name of the step.
        """
        super().__init__(component=component, name=name, subdir=subdir)
        self.cull_mesh_step = cull_mesh_step

        self.add_input_file(
            filename='graph.info',
            work_dir_target=os.path.join(
                cull_mesh_step.path, 'culled_ocean_graph.info'
            ),
        )

    def setup(self):
        """
        Refuse a model whose packaging is not supported, before anything runs.
        """
        super().setup()
        check_ocean_model(self.config)
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
        Partition the graph into each core count.
        """
        super().run()
        check_ocean_model(self.config)
        config = self.config
        logger = self.logger

        # the graph is staged beside its partitions, under the name they carry
        shutil.copyfile('graph.info', GRAPH_BASENAME)

        ncells = read_graph_cell_count('graph.info')
        section = config['component_inputs']
        cores = get_core_list(
            ncells=ncells,
            max_cells_per_core=section.getint('max_cells_per_core'),
            min_cells_per_core=section.getint('min_cells_per_core'),
        )
        if cores.max() > ncells:
            raise ValueError(
                f'Cannot partition {ncells} cells into {cores.max()} pieces.'
            )

        remaining = partitions_to_build(cores, GRAPH_BASENAME, ncells)
        done = len(cores) - len(remaining)
        logger.info(
            f'Partitioning {ncells} cells into {cores.min()} to '
            f'{cores.max()} pieces: {len(remaining)} to build, '
            f'{self.cpus_per_task} at a time'
            + (f', {done} already complete' if done else '')
        )

        build_partitions(
            regions=[RegionGraph(filename='graph.info')],
            cores=remaining,
            basename=GRAPH_BASENAME,
            ncells=ncells,
            process_count=self.cpus_per_task,
            logger=logger,
        )
