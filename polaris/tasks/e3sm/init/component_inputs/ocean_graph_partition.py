import os
import shutil

from mpas_tools.logging import check_call

from polaris import Step
from polaris.tasks.e3sm.init.component_inputs.models import check_ocean_model
from polaris.tasks.e3sm.init.component_inputs.partitions import (
    get_core_list,
    read_graph_cell_count,
)

#: The base name ``gpmetis`` partitions, and so the stem of every partition
#: file this step writes.  The creation date is added when the files are
#: staged, not here.
GRAPH_BASENAME = 'mpas-o.graph.info'


class OceanGraphPartitionStep(Step):
    """
    A step for partitioning the ocean graph into the core counts E3SM runs use.

    The graph itself comes from the cull step -- the ``ocean`` prefix, which is
    the domain the ocean initial condition is built on -- so nothing is
    regenerated here; this runs ``gpmetis`` over it once per core count.

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

    def run(self):
        """
        Partition the graph into each core count.
        """
        super().run()
        check_ocean_model(self.config)
        config = self.config
        logger = self.logger

        # gpmetis names its output after its input, so the partitions are
        # named by copying the graph to the name they should carry
        shutil.copyfile('graph.info', GRAPH_BASENAME)

        ncells = read_graph_cell_count('graph.info')
        section = config['component_inputs']
        cores = get_core_list(
            ncells=ncells,
            max_cells_per_core=section.getint('max_cells_per_core'),
            min_cells_per_core=section.getint('min_cells_per_core'),
        )
        logger.info(
            f'Partitioning {ncells} cells into {cores.min()} to '
            f'{cores.max()} pieces'
        )

        for ncores in cores:
            if ncores > ncells:
                raise ValueError(
                    f'Cannot partition {ncells} cells into {ncores} pieces.'
                )
            out_filename = f'{GRAPH_BASENAME}.part.{ncores}'
            if os.path.exists(out_filename):
                continue
            if ncores == 1:
                # gpmetis will not make a one-piece partition, and an empty
                # file is what MPAS reads as "every cell on one task"
                with open(out_filename, 'w'):
                    pass
            else:
                check_call(['gpmetis', GRAPH_BASENAME, f'{ncores}'], logger)
