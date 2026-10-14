import os
from typing import Any, Dict, List, Tuple

from polaris.config import PolarisConfigParser
from polaris.step import Step
from polaris.tasks.ocean.realistic_global.forward.forward import Forward
from polaris.tasks.ocean.realistic_global.forward.initial_condition import (
    StepInitialCondition,
)
from polaris.tasks.ocean.realistic_global.forward.stage import ForwardStage
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

from .schedule import load_schedule_stages
from .validate import StageCheck, Validate
from .viz import VizDynamicAdjustmentStep

CONFIG_FILENAME = 'realistic_global_dynamic_adjustment.cfg'
CONFIG_PACKAGE = 'polaris.tasks.ocean.realistic_global.dynamic_adjustment'
FORWARD_CONFIG_FILENAME = 'realistic_global_forward.cfg'
FORWARD_CONFIG_PACKAGE = 'polaris.tasks.ocean.realistic_global.forward'

# The variables the final ``simulation`` stage compares against a baseline.
VALIDATE_VARS = [
    'temperature',
    'salinity',
    'layerThickness',
    'normalVelocity',
]


def get_realistic_dynamic_adjustment_steps(
    component: Any, mesh_name: str, include_viz: bool = False
) -> Tuple[Dict[str, Step], PolarisConfigParser, List[ForwardStage]]:
    """
    Get shared steps for the realistic global ocean dynamic-adjustment
    workflow for one MPAS mesh.

    Composes the full dependency chain:

    * The shared ``realistic_global/init`` steps (via
      :py:func:`~polaris.tasks.ocean.realistic_global.init.steps.get_realistic_init_steps`)
    * One
      :py:class:`~polaris.tasks.ocean.realistic_global.forward.forward.Forward`
      stage per schedule entry, chained by restart
    * A :py:class:`.StageCheck` after each stage
    *
      :py:class:`~polaris.tasks.ocean.realistic_global.dynamic_adjustment.validate.Validate`
    * :py:class:`.VizDynamicAdjustmentStep`

    All steps are created via
    :py:meth:`polaris.Component.get_or_create_shared_step`, and the config via
    :py:meth:`polaris.Component.get_or_create_shared_config`, so a downstream
    workflow that wants the adjusted restart -- ``e3sm/init``'s component
    inputs, say -- gets the same step instances rather than a second copy of a
    very expensive chain.  This is why the caller receives the stages as well:
    the last one's ``restart_out`` is the file such a workflow is after, and
    which stage that is depends on the schedule.

    Calling this again for the same mesh is a no-op that hands back what
    already exists, including the restart chain's dependencies.

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        The ocean component the steps belong to.

    mesh_name : str
        The name of the MPAS mesh (e.g. ``'icos240km'``).

    include_viz : bool, optional
        Whether to include the (shared) :py:class:`.VizDynamicAdjustmentStep`
        in the returned steps.  The step is always created so it is part of the
        workflow, but it is only returned -- and so only in a task's
        ``steps_to_run`` -- when this is ``True``.  A figure describing a
        completed adjustment is not what a workflow that only wants the relaxed
        restart is asking about, so those consumers leave it ``False``.

    Returns
    -------
    steps : dict of {str: polaris.Step}
        All steps keyed by their suggested symlink names.

    config : polaris.config.PolarisConfigParser
        Per-mesh shared config for the dynamic-adjustment steps.  It also
        carries the ``[realistic_global_forward]`` options, since a stage is a
        forward run.

    stages : list of ForwardStage
        The stages of the adjustment, in schedule order.
    """
    base_subdir = adjustment_subdir(mesh_name)
    config = _get_dynamic_adjustment_config(
        component, base_subdir, CONFIG_FILENAME, mesh_name
    )
    init_steps, _ = get_realistic_init_steps(
        component=component, mesh_name=mesh_name, include_viz=False
    )
    steps: Dict[str, Step] = dict(init_steps)

    init_step = init_steps['initial_state']
    forcing_step = init_steps['forcing']
    min_res = min_res_for_mesh(mesh_name)
    approx_cell_count = estimate_ocean_cell_count(mesh_name)

    stages = load_schedule_stages(mesh_name, config)

    previous = None
    for stage in stages:
        forward_step = component.get_or_create_shared_step(
            step_cls=Forward,
            subdir=os.path.join(base_subdir, stage.name),
            config=config,
            config_filename=CONFIG_FILENAME,
            name=stage.name,
            init_condition=StepInitialCondition(
                init_step,
                min_res=min_res,
                approx_cell_count=approx_cell_count,
                forcing_step=forcing_step,
            ),
            stage=stage,
            validate_vars=(
                VALIDATE_VARS if stage.name == 'simulation' else None
            ),
        )
        # the restart chain, which cannot be expressed as an input/output pair
        # because the restart filename comes from the schedule rather than
        # from the step.  Re-wiring it on a later call is a no-op.
        if previous is not None:
            forward_step.add_dependency(previous, previous.name)
        steps[forward_step.name] = forward_step
        previous = forward_step

        # checked as soon as it finishes, so a stage that is already out of
        # bounds stops the sequence instead of costing the whole job.  A
        # separate step because an MPI step should not carry Python work after
        # the model exits.
        check_step = component.get_or_create_shared_step(
            step_cls=StageCheck,
            subdir=os.path.join(base_subdir, f'{stage.name}_check'),
            config=config,
            config_filename=CONFIG_FILENAME,
            stage=stage,
            sequence_start=stages[0].start_time,
        )
        check_step.add_dependency(forward_step, forward_step.name)
        steps[check_step.name] = check_step

    validate_step = component.get_or_create_shared_step(
        step_cls=Validate,
        subdir=os.path.join(base_subdir, 'validate'),
        config=config,
        config_filename=CONFIG_FILENAME,
        stages=stages,
    )
    steps[validate_step.name] = validate_step

    viz_step = component.get_or_create_shared_step(
        step_cls=VizDynamicAdjustmentStep,
        subdir=os.path.join(base_subdir, 'viz'),
        config=config,
        config_filename=CONFIG_FILENAME,
        stages=stages,
    )
    if include_viz:
        steps[viz_step.name] = viz_step

    return steps, config, stages


def adjustment_subdir(mesh_name: str) -> str:
    """
    The work directory the dynamic-adjustment steps for a mesh live under.

    Parameters
    ----------
    mesh_name : str
        The name of the MPAS mesh.

    Returns
    -------
    str
        The subdirectory, relative to the component.
    """
    return f'spherical/realistic_global/{mesh_name}/dynamic_adjustment'


def _get_dynamic_adjustment_config(
    component: Any, subdir: str, config_filename: str, mesh_name: str
) -> PolarisConfigParser:
    """
    Get or create the shared per-mesh config for the dynamic-adjustment steps.

    A stage is a forward run, so the config carries the
    ``[realistic_global_forward]`` options as well as its own.  The per-mesh
    overrides from
    :py:mod:`polaris.tasks.ocean.realistic_global.mesh_configs` come last so
    that they win.

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        The ocean component.

    subdir : str
        The subdirectory path for this mesh's dynamic-adjustment steps.

    config_filename : str
        The config filename (symlinked in each step's work directory).

    mesh_name : str
        The name of the MPAS mesh, used to find per-mesh overrides.

    Returns
    -------
    polaris.config.PolarisConfigParser
    """
    filepath = os.path.join(component.name, subdir, config_filename)
    if filepath in component.configs:
        return component.configs[filepath]
    config = PolarisConfigParser(filepath=filepath)
    config.add_from_package(FORWARD_CONFIG_PACKAGE, FORWARD_CONFIG_FILENAME)
    config.add_from_package(CONFIG_PACKAGE, config_filename)
    add_realistic_global_mesh_config(config=config, mesh_name=mesh_name)
    return config
