from polaris import (
    Step as Step,
)
from polaris import (
    Task as Task,
)
from polaris.config import PolarisConfigParser as PolarisConfigParser

# from polaris.tasks.ocean.realistic_global.stats_analysis import (
#    StatsAnalysis as StatsAnalysis
# )
from polaris.tasks.ocean.realistic_global.forward import Forward as Forward


class AnalysisMembers(Task):
    """ """

    def __init__(
        self,
        component,
        subdir,
        mesh_name,
        config,
        config_filename,
    ):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this task belongs to
        subdir : str
            The subdirectory for the task
        test_name : str
            The name of the test (e.g., 'munk')
        config : PolarisConfigParser
            The configuration parser for the task
        config_filename : str
            The name of the configuration file
        """
        subdir = f'{subdir}/analysis_members/{mesh_name}'
        super().__init__(
            component=component, name='analysis_test', subdir=subdir
        )

        self.set_shared_config(config, link=config_filename)

        package = 'polaris.tasks.ocean.realistic_global'
        forward_step = Forward(
            component=component,
            package=package,
            indir=subdir,
            mesh_filename='culled_graph.info',
            init_filename='culled_graph.info',
            graph_filename='culled_graph.info',
        )
        forward_step.set_shared_config(config, link=config_filename)
        self.add_step(forward_step)


#        stats_analysis = StatsAnalysis(
#            component=component,
#            indir=indir,
#            test_name=test_name,
#        )
#        analysis.set_shared_config(config, link=config_filename)
#        self.add_step(analysis, run_by_default=False)
