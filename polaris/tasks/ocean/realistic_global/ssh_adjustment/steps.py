import os
from functools import partial
from typing import Any, Dict, Tuple

from polaris.config import PolarisConfigParser
from polaris.step import Step
from polaris.tasks.e3sm.init.topo.cull.steps import get_cull_topo_steps
from polaris.tasks.ocean.realistic_global.cavities import (
    copy_antarctic_boundary_convention,
)
from polaris.tasks.ocean.realistic_global.forward.initial_condition import (
    StepInitialCondition,
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
from polaris.tasks.ocean.realistic_global.models import (
    DEFAULT_MODEL,
    model_subdir,
)

from .adjust import RealisticSshAdjustment
from .forward import SshForward

CONFIG_FILENAME = 'ssh_adjustment.cfg'
CONFIG_PACKAGE = 'polaris.tasks.ocean.realistic_global.ssh_adjustment'
FORWARD_CONFIG_FILENAME = 'forward.cfg'
FORWARD_CONFIG_PACKAGE = 'polaris.tasks.ocean.realistic_global.forward'


def get_realistic_ssh_adjustment_steps(
    component: Any,
    mesh_name: str,
    model: str = DEFAULT_MODEL,
) -> Tuple[Dict[str, Step], PolarisConfigParser, str]:
    """
    Get the shared steps that adjust the SSH under land ice to the land-ice
    pressure for one MPAS mesh.

    The steps are pairs of an
    :py:class:`~polaris.tasks.ocean.realistic_global.ssh_adjustment.forward.SshForward`
    step from rest and a :py:class:`.RealisticSshAdjustment`, one pair for
    each of ``[ssh_adjustment] iterations``.  The first step starts from
    the ``initial_state`` step's ``init.nc`` and each later one from the
    adjustment before it.  Every ``realistic_global`` ocean run with
    ice-shelf cavities starts from the last adjustment's output, which is
    returned as ``adjusted_target``.

    The steps are created with
    :py:meth:`polaris.Component.get_or_create_shared_step`, so the
    ``ssh_adjustment``, ``dynamic_adjustment`` and ``forward`` tasks of a mesh
    share them.  They live in a directory named for the ocean model, like
    the ``init`` steps they read.

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        The ocean component the steps belong to.

    mesh_name : str
        The name of the MPAS mesh (e.g. ``'qu240km'``).

    model : str, optional
        The ocean model to build the steps for.

    Returns
    -------
    steps : dict of {str: polaris.Step}
        The SSH-adjustment steps, keyed by their names, in the order they run

    config : polaris.config.PolarisConfigParser
        The shared config of the steps

    adjusted_target : str
        The adjusted initial state, relative to the base work directory
    """
    init_steps, _ = get_realistic_init_steps(
        component=component,
        mesh_name=mesh_name,
        include_viz=False,
        model=model,
    )
    base_subdir = model_subdir(ssh_adjustment_subdir(mesh_name), model)
    config = get_ssh_adjustment_config(component, mesh_name, model)
    iterations = config.getint('ssh_adjustment', 'iterations')

    init_step = init_steps['initial_state']
    forcing_step = init_steps['forcing']
    min_res = min_res_for_mesh(mesh_name)
    approx_cell_count = estimate_ocean_cell_count(mesh_name)

    steps: Dict[str, Step] = {}
    init_target = f'{init_step.path}/init.nc'
    for iteration in range(iterations):
        name = f'ssh_forward_{iteration}'
        forward_step = component.get_or_create_shared_step(
            step_cls=SshForward,
            subdir=os.path.join(base_subdir, name),
            config=config,
            config_filename=CONFIG_FILENAME,
            name=name,
            init_condition=StepInitialCondition(
                init_step,
                min_res=min_res,
                approx_cell_count=approx_cell_count,
                forcing_step=forcing_step,
                init_target=init_target,
            ),
        )
        steps[name] = forward_step

        name = f'ssh_adjust_{iteration}'
        adjust_step = component.get_or_create_shared_step(
            step_cls=RealisticSshAdjustment,
            subdir=os.path.join(base_subdir, name),
            config=config,
            config_filename=CONFIG_FILENAME,
            mesh_filename=f'{init_step.path}/mesh.nc',
            forward=forward_step,
            name=name,
        )
        steps[name] = adjust_step
        init_target = f'{adjust_step.path}/output.nc'
    return steps, config, init_target


def add_ssh_adjustment_steps(task, mesh_name, model, forward_step):
    """
    Add the SSH-adjustment steps to a task, and start its forward step from
    their adjusted initial state.

    Whether the ocean has ice-shelf cavities is only known once a user's
    config has been read, so a task calls this from its ``configure()``
    method when it does.

    Parameters
    ----------
    task : polaris.Task
        The task, during ``configure()``.

    mesh_name : str
        The name of the MPAS mesh.

    model : str
        The ocean model the task's init steps are for.

    forward_step : polaris.tasks.ocean.realistic_global.forward.forward.Forward
        The task's forward step, whose initial condition reads the init
        steps.
    """
    init_condition = forward_step.init_condition
    if not isinstance(init_condition, StepInitialCondition):
        raise TypeError(
            f'{task.path} has ice-shelf cavities but does not start from the '
            f'realistic_global init steps, so it cannot start from adjusted '
            f'SSH.'
        )
    steps, _, adjusted_target = get_realistic_ssh_adjustment_steps(
        component=task.component, mesh_name=mesh_name, model=model
    )
    for name, step in steps.items():
        if name not in task.steps:
            task.add_step(step, symlink=name)
    forward_step.set_init_condition(
        StepInitialCondition(
            init_condition.init_step,
            min_res=init_condition.min_res,
            approx_cell_count=init_condition.approx_cell_count,
            forcing_step=init_condition.forcing_step,
            init_target=adjusted_target,
        )
    )


def ssh_adjustment_subdir(mesh_name: str) -> str:
    """
    The work directory of a mesh's SSH-adjustment task.  Its steps live in a
    directory under it named for their ocean model.

    Parameters
    ----------
    mesh_name : str
        The name of the MPAS mesh.

    Returns
    -------
    str
        The subdirectory, relative to the component.
    """
    return f'spherical/realistic_global/{mesh_name}/ssh_adjustment'


def get_ssh_adjustment_config(
    component: Any, mesh_name: str, model: str
) -> PolarisConfigParser:
    """
    Get or create the shared config for one model's SSH-adjustment steps.

    The forward steps are ``realistic_global`` forward runs, so the config
    carries the ``[realistic_global_forward]`` options and the ice-shelf
    cavity options as well as its own.  The per-mesh overrides come last so
    that they win.

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        The ocean component.

    mesh_name : str
        The name of the MPAS mesh, used to find per-mesh overrides.

    model : str
        The ocean model the steps are for.

    Returns
    -------
    polaris.config.PolarisConfigParser
    """
    subdir = model_subdir(ssh_adjustment_subdir(mesh_name), model)
    filepath = os.path.join(component.name, subdir, CONFIG_FILENAME)
    return component.get_or_create_shared_config(
        filepath=filepath,
        create=partial(_build_config, filepath=filepath, mesh_name=mesh_name),
    )


def _build_config(filepath: str, mesh_name: str) -> PolarisConfigParser:
    """
    Build the SSH-adjustment config, with the per-mesh overrides last and
    the Antarctic boundary convention copied from the cull step's config.
    """
    config = PolarisConfigParser(filepath=filepath)
    config.add_from_package(FORWARD_CONFIG_PACKAGE, FORWARD_CONFIG_FILENAME)
    config.add_from_package(
        'polaris.tasks.ocean.realistic_global', 'cavities.cfg'
    )
    config.add_from_package(CONFIG_PACKAGE, CONFIG_FILENAME)
    add_realistic_global_mesh_config(config=config, mesh_name=mesh_name)
    _, cull_config = get_cull_topo_steps(
        mesh_name=mesh_name, include_viz=False
    )
    copy_antarctic_boundary_convention(config, cull_config)
    return config
