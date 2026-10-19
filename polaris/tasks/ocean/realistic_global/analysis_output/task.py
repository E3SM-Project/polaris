from typing import TYPE_CHECKING, Dict, Optional

from polaris import Task
from polaris.config import PolarisConfigParser
from polaris.mesh.base import get_base_mesh_step_names
from polaris.mesh.spherical.unified import UNIFIED_MESH_NAMES
from polaris.tasks.ocean.realistic_global.analysis_output.forward import (
    AnalysisOutputForward,
)
from polaris.tasks.ocean.realistic_global.analysis_output.restart import (
    AnalysisRestart,
)
from polaris.tasks.ocean.realistic_global.analysis_output.sampling import (
    SamplingConvergence,
)
from polaris.tasks.ocean.realistic_global.forward import (
    InitialCondition,
    StatsAnalysis,
    StepInitialCondition,
)
from polaris.tasks.ocean.realistic_global.forward.tasks import (
    CACHED_MESHES,
    get_cached_initial_condition,
)
from polaris.tasks.ocean.realistic_global.init.steps import (
    get_realistic_init_steps,
)
from polaris.tasks.ocean.realistic_global.mesh_configs import (
    add_realistic_global_mesh_config,
)
from polaris.tasks.ocean.realistic_global.mesh_info import (
    estimate_ocean_cell_count,
    min_res_for_mesh,
)

if TYPE_CHECKING:
    from polaris import Step

#: The mesh of the restart and sampling_convergence tasks, which need only
#: one, and the cheapest
SHORT_TEST_MESH = 'e3sm-qu240'


def add_realistic_global_analysis_output_tasks(component):
    """
    Add an :py:class:`AnalysisOutput` task for each mesh with a cached
    initial condition and for each mesh the ``init`` workflow builds, and
    the :py:class:`AnalysisRestart` and :py:class:`SamplingConvergence` tasks
    on ``e3sm-qu240``

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        The ocean component to add the tasks to
    """
    for mesh_name in CACHED_MESHES:
        init_condition: InitialCondition = get_cached_initial_condition(
            mesh_name
        )
        component.add_task(
            AnalysisOutput(
                component=component,
                mesh_name=mesh_name,
                init_condition=init_condition,
            )
        )
        if mesh_name == SHORT_TEST_MESH:
            component.add_task(
                AnalysisRestart(
                    component=component,
                    mesh_name=mesh_name,
                    init_condition=init_condition,
                )
            )
            component.add_task(
                SamplingConvergence(
                    component=component,
                    mesh_name=mesh_name,
                    init_condition=init_condition,
                )
            )

    # the same meshes as the forward tasks, each running from the initial
    # condition the shared init steps build
    mesh_names = list(get_base_mesh_step_names()) + list(UNIFIED_MESH_NAMES)
    for mesh_name in mesh_names:
        init_steps, _ = get_realistic_init_steps(
            component=component, mesh_name=mesh_name, include_viz=False
        )
        init_condition = StepInitialCondition(
            init_steps['initial_state'],
            min_res=min_res_for_mesh(mesh_name),
            approx_cell_count=estimate_ocean_cell_count(mesh_name),
            forcing_step=init_steps['forcing'],
        )
        component.add_task(
            AnalysisOutput(
                component=component,
                mesh_name=mesh_name,
                init_condition=init_condition,
                init_steps=init_steps,
            )
        )


class AnalysisOutput(Task):
    """
    A one-year Omega run that writes the monthly means, overturning
    streamfunction and daily global statistics the ocean analysis reads

    The run's settings come from ``[realistic_global_forward]`` and the
    defaults in ``analysis_output.cfg``, with the mesh's options and then
    ``one_year.cfg`` layered on top.  Only the ``forward`` step runs by
    default; ``global_stats`` plots the daily statistics.
    """

    def __init__(
        self,
        component,
        mesh_name: str,
        init_condition: InitialCondition,
        init_steps: Optional[Dict[str, 'Step']] = None,
    ):
        """
        Create the task

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the task belongs to

        mesh_name : str
            The name of the mesh (e.g. ``e3sm-qu240``)

        init_condition : InitialCondition
            The source of the model input files

        init_steps : dict of polaris.Step, optional
            Shared upstream steps to add to the task, keyed by the symlink name
            to give them.  Needed when ``init_condition`` consumes their
            outputs, and left unset for a cached initial condition.
        """
        subdir = (
            f'spherical/realistic_global/{mesh_name}/analysis_output/1_year'
        )
        super().__init__(
            component=component,
            name='analysis_output_1_year',
            subdir=subdir,
        )

        config_filename = 'analysis_output.cfg'
        config_path = f'{component.name}/{subdir}/{config_filename}'
        config = PolarisConfigParser(filepath=config_path)
        config.add_from_package(
            'polaris.tasks.ocean.realistic_global.forward',
            'forward.cfg',
        )
        config.add_from_package(
            'polaris.tasks.ocean.realistic_global.analysis_output',
            config_filename,
        )
        add_realistic_global_mesh_config(config=config, mesh_name=mesh_name)
        config.add_from_package(
            'polaris.tasks.ocean.realistic_global.analysis_output',
            'one_year.cfg',
        )
        self.set_shared_config(config, link=config_filename)

        # the shared init steps carry their own init.cfg
        if init_steps is not None:
            for symlink, step in init_steps.items():
                self.add_step(step, symlink=symlink)

        forward_step = AnalysisOutputForward(
            component=component,
            init_condition=init_condition,
            subdir=f'{subdir}/forward',
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
