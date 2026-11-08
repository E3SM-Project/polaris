import os

from polaris.config import PolarisConfigParser
from polaris.resolution import resolution_to_string
from polaris.tasks.landice.mismip_plus.init import Init
from polaris.tasks.landice.mismip_plus.spin_up.run import SpinUpRun
from polaris.tasks.landice.mismip_plus.spin_up.spin_up import SpinUp
from polaris.tasks.mesh.planar.mismip_plus import get_mismip_plus_mesh_steps


def get_mismip_plus_steady_state_steps(resolution, component=None):
    """
    Get the shared steps that make the MISMIP+ steady state at a given
    resolution.  The steady state is the output of the ``spin_up`` step,
    which is cached.

    Parameters
    ----------
    resolution : float
        The nominal resolution of the mesh in km

    component : polaris.Component, optional
        The component that owns the shared steps.  Defaults to ``landice``.

    Returns
    -------
    steps : dict of str to polaris.Step
        The steps that make the steady state, keyed by logical step name:
        ``mesh``, ``init``, ``spin_up_run`` and ``spin_up``

    config : polaris.config.PolarisConfigParser
        The shared config options for MISMIP+
    """
    if component is None:
        from polaris.tasks.landice import landice as component

    resdir = f'mismip_plus/{resolution_to_string(resolution)}'
    config_filename = 'mismip_plus.cfg'
    filepath = os.path.join(component.name, resdir, config_filename)

    def create():
        config = PolarisConfigParser(filepath=filepath)
        config.add_from_package(
            'polaris.tasks.landice.mismip_plus', config_filename
        )
        return config

    config = component.get_or_create_shared_config(
        filepath=filepath, create=create
    )

    mesh_steps, _ = get_mismip_plus_mesh_steps(resolution=resolution)
    mesh_step = mesh_steps['mesh']

    init = component.get_or_create_shared_step(
        step_cls=Init,
        subdir=f'{resdir}/init',
        config=config,
        config_filename=config_filename,
        mesh_step=mesh_step,
    )
    spin_up_run = component.get_or_create_shared_step(
        step_cls=SpinUpRun,
        subdir=f'{resdir}/spin_up/run',
        config=config,
        config_filename=config_filename,
        init=init,
        mesh_step=mesh_step,
    )
    spin_up = component.get_or_create_shared_step(
        step_cls=SpinUp,
        subdir=f'{resdir}/spin_up/spin_up',
        config=config,
        config_filename=config_filename,
        run_step=spin_up_run,
    )
    steps = dict(
        mesh=mesh_step,
        init=init,
        spin_up_run=spin_up_run,
        spin_up=spin_up,
    )
    return steps, config
