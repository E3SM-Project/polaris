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
from polaris.tasks.ocean.realistic_global.viz import Viz as Viz


class AnalysisMembers(Task):
    """
    A task for exercising the global-statistics analysis member on a
    realistic global mesh.

    The task runs the ocean model forward from a cached initial condition
    with the global-statistics analysis member enabled, then plots time
    series of the resulting statistics and global maps of the state
    variables.  Only the ``forward`` step runs by default.
    """

    def __init__(
        self,
        component,
        subdir,
        mesh_name,
        mpaso_id,
        omega_id,
        ncells,
    ):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this task belongs to

        subdir : str
            The subdirectory for the task, to which
            ``analysis_members_test`` will be appended

        mesh_name : str
            The name of the mesh (e.g. ``QU.240km``)

        mpaso_id : int
            The ID of the MPAS-Ocean initial condition in the Polaris input
            database

        omega_id : int
            The ID of the Omega initial condition in the Polaris input
            database

        ncells : int
            The approximate number of cells in the mesh, used to constrain
            resources
        """
        subdir = f'{subdir}/analysis_members_test'
        super().__init__(
            component=component, name='analysis_test', subdir=subdir
        )

        config_filename = 'analysis_members.cfg'
        config_path = f'{component.name}/{subdir}/{config_filename}'
        config = PolarisConfigParser(filepath=config_path)
        config.add_from_package(
            'polaris.tasks.ocean.realistic_global',
            'realistic_global.cfg',
        )
        config.add_from_package(
            'polaris.tasks.ocean.realistic_global.analysis_members',
            config_filename,
        )

        mesh_info = {
            'QU.240km': dict(
                dt='02:00:00',
                btr_dt='00:04:00',
                run_duration='0005_00:00:00',
            ),
            'EC30to60E2r2': dict(
                dt='00:30:00',
                btr_dt='00:01:00',
                run_duration='0001_00:00:00',
            ),
        }
        package = 'polaris.tasks.ocean.realistic_global'
        replacements = {
            'time_integrator': 'SplitExplicitRK2',
            'run_duration': mesh_info[mesh_name]['run_duration'],
            'dt': mesh_info[mesh_name]['dt'],
            'btr_dt': mesh_info[mesh_name]['btr_dt'],
            'output_interval': '0001_00:00:00',
            'output_freq': '1',
            'output_freq_units': 'days',
        }
        forward_step = Forward(
            component=component,
            package=package,
            indir=subdir,
            mesh_name=mesh_name,
            mpaso_id=mpaso_id,
            omega_id=omega_id,
            ncells=ncells,
            replacements=replacements,
        )
        forward_step.set_shared_config(config, link=config_filename)
        self.add_step(forward_step)

        stats_analysis = StatsAnalysis(
            component=component,
            indir=subdir,
            forward_step=forward_step,
        )
        stats_analysis.set_shared_config(config, link=config_filename)
        self.add_step(stats_analysis, run_by_default=False)

        viz = Viz(
            component=component,
            indir=subdir,
            forward=forward_step,
        )
        viz.set_shared_config(config, link=config_filename)
        self.add_step(viz, run_by_default=False)
