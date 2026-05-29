from polaris import (
    Step as Step,
)
from polaris import (
    Task as Task,
)
from polaris.config import PolarisConfigParser as PolarisConfigParser
from polaris.tasks.ocean.realistic_global.analysis_members.stats_analysis import (  # noqa: E501
    StatsAnalysis as StatsAnalysis,
)
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
        subdir = f'{subdir}/analysis_members_test'
        super().__init__(
            component=component, name='analysis_test', subdir=subdir
        )

        self.set_shared_config(config, link=config_filename)

        package = 'polaris.tasks.ocean.realistic_global'
        replacements = {
            'run_duration': '0030_00-00-00',
            'dt': '00:10:00',  # TODO use dt_per_km config option
            'output_freq': '1',
            'output_freq_units': 'seconds',
        }
        forward_step = Forward(
            component=component,
            package=package,
            indir=subdir,
            name=f'{mesh_name}_forward',
            mesh_filename='ocean.QU.240km.151209.omega.teos10eos.nc',
            init_filename='ocean.QU.240km.151209.omega.teos10eos.nc',
            output_filename='output.nc',
            replacements=replacements,
            resolution_for_cell_count=240,
        )
        forward_step.set_shared_config(config, link=config_filename)
        self.add_step(forward_step)

        stats_analysis = StatsAnalysis(
            component=component,
            name=f'{mesh_name}_global_stats',
            indir=subdir,
            output_filename='output.nc',
            forward_step=forward_step,
        )
        stats_analysis.set_shared_config(config, link=config_filename)
        self.add_step(stats_analysis, run_by_default=False)
