from polaris import (
    Step as Step,
)
from polaris import (
    Task as Task,
)
from polaris.config import PolarisConfigParser as PolarisConfigParser
from polaris.tasks.ocean.realistic_global.analysis_members.forward import (
    DURATIONS as DURATIONS,
)
from polaris.tasks.ocean.realistic_global.analysis_members.forward import (
    AnalysisMembersForward as AnalysisMembersForward,
)
from polaris.tasks.ocean.realistic_global.analysis_members.forward import (
    Forward as Forward,
)
from polaris.tasks.ocean.realistic_global.forward.stats_analysis import (
    StatsAnalysis as StatsAnalysis,
)
from polaris.tasks.ocean.realistic_global.forward.viz import Viz as Viz


class AnalysisMembers(Task):
    """
    A task for exercising the analysis members on a realistic global mesh.

    The task runs the ocean model forward from a cached initial condition
    with the global-statistics analysis member enabled, then plots time
    series of the resulting statistics.  The ``short`` run, which supports
    both MPAS-Ocean and Omega, also plots global maps of the state
    variables.  The ``1_year`` run supports only Omega and also writes the
    monthly means and overturning streamfunction the ocean analysis reads.
    Only the ``forward`` step runs by default.
    """

    def __init__(
        self,
        component,
        subdir,
        mesh_name,
        mpaso_id,
        omega_id,
        ncells,
        duration,
    ):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this task belongs to

        subdir : str
            The subdirectory for the mesh, to which
            ``analysis_members/<duration>`` will be appended

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

        duration : str
            The duration of the run, one of ``DURATIONS``
        """
        subdir = f'{subdir}/analysis_members/{duration}'
        super().__init__(
            component=component,
            name=f'analysis_members_{duration}',
            subdir=subdir,
        )

        package = 'polaris.tasks.ocean.realistic_global.analysis_members'
        config_filename = 'analysis_members.cfg'
        config_path = f'{component.name}/{subdir}/{config_filename}'
        config = PolarisConfigParser(filepath=config_path)
        config.add_from_package(
            'polaris.tasks.ocean.realistic_global',
            'realistic_global.cfg',
        )
        config.add_from_package(package, config_filename)
        config.add_from_package(package, f'{mesh_name}.cfg')
        self.set_shared_config(config, link=config_filename)

        forward_step = AnalysisMembersForward(
            component=component,
            indir=subdir,
            mesh_name=mesh_name,
            mpaso_id=mpaso_id,
            omega_id=omega_id,
            ncells=ncells,
            duration=duration,
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

        # the one-year run writes monthly snapshots rather than the single
        # output.nc the viz step reads
        if duration == 'short':
            viz = Viz(
                component=component,
                indir=subdir,
                forward=forward_step,
            )
            viz.set_shared_config(config, link=config_filename)
            self.add_step(viz, run_by_default=False)
