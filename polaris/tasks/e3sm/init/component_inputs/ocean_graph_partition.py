import os

from polaris.e3sm.init.graph_partition import GraphPartitionStep
from polaris.tasks.e3sm.init.component_inputs.models import check_ocean_model

#: The stem of every partition file this step writes, and the name the graph
#: is staged under beside them.  The creation date is added when the files
#: are staged, not here.
GRAPH_BASENAME = 'mpas-o.graph.info'


class OceanGraphPartitionStep(GraphPartitionStep):
    """
    A step for partitioning the ocean graph into the core counts E3SM runs use.

    The graph itself comes from the cull step -- the ``ocean`` prefix, which is
    the domain the ocean initial condition is built on -- so nothing is
    regenerated here.

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
        super().__init__(
            component=component,
            name=name,
            subdir=subdir,
            basename=GRAPH_BASENAME,
            section='component_inputs',
            graph_target=os.path.join(
                cull_mesh_step.path, 'culled_ocean_graph.info'
            ),
        )
        self.cull_mesh_step = cull_mesh_step

    def setup(self):
        """
        Refuse a model whose packaging is not supported, before anything runs.
        """
        super().setup()
        check_ocean_model(self.config)

    def run(self):
        """
        Partition the ocean graph into each core count.
        """
        check_ocean_model(self.config)
        super().run()
