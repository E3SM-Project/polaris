from typing import TYPE_CHECKING, Dict, Optional

from polaris import Task
from polaris.config import PolarisConfigParser
from polaris.tasks.ocean.realistic_global.forward.forward import Forward
from polaris.tasks.ocean.realistic_global.forward.initial_condition import (
    InitialCondition,
)
from polaris.tasks.ocean.realistic_global.mesh_configs import (
    add_realistic_global_mesh_config,
)

if TYPE_CHECKING:
    from polaris import Step


class RealisticGlobalForward(Task):
    """
    A short forward run of the configured ocean model for a realistic global
    ocean simulation on one MPAS mesh.

    The task runs a single
    :py:class:`~polaris.tasks.ocean.realistic_global.forward.forward.Forward`
    step (``short``, a brief smoke test) whose duration and cadence come from
    the ``[realistic_global_forward]`` config section, with any per-mesh
    overrides applied on top.  The target model is resolved from
    ``[ocean] model`` during component setup.

    Where the model's input files come from is the initial condition's
    business, not the task's, which is what lets one task cover two rather
    different costs.  A ``StepInitialCondition`` consumes the outputs of the
    shared ``realistic_global/init`` steps, which the caller passes as
    ``init_steps`` so the task is runnable end to end; a
    ``DatabaseInitialCondition`` downloads a cached initial condition and needs
    no upstream steps at all.

    Attributes
    ----------
    mesh_name : str
        The name of the MPAS mesh.
    """

    def __init__(
        self,
        component,
        mesh_name: str,
        init_condition: InitialCondition,
        subdir_name: str = 'forward',
        init_steps: Optional[Dict[str, 'Step']] = None,
    ):
        """
        Create the task.

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the task belongs to.

        mesh_name : str
            The name of the MPAS mesh (e.g. ``'icos240km'``).

        init_condition : InitialCondition
            The source of the model input files.

        subdir_name : str, optional
            The name of the task's directory under the mesh.  It also keeps
            two tasks on the same mesh apart when they differ only in where
            their initial condition comes from.

        init_steps : dict of polaris.Step, optional
            Shared upstream steps to add to the task, keyed by the symlink name
            to give them.  Needed when ``init_condition`` consumes their
            outputs, and left unset for a source that does not.
        """
        base = f'spherical/realistic_global/{mesh_name}/{subdir_name}'
        super().__init__(
            component=component,
            name='realistic_global_forward',
            subdir=f'{base}/task',
        )
        self.mesh_name = mesh_name

        config_filename = 'realistic_global_forward.cfg'
        filepath = f'{component.name}/{base}/{config_filename}'
        config = PolarisConfigParser(filepath=filepath)
        config.add_from_package(
            'polaris.tasks.ocean.realistic_global.forward', config_filename
        )
        add_realistic_global_mesh_config(config=config, mesh_name=mesh_name)
        self.set_shared_config(config, link=config_filename)

        # the shared init steps carry their own realistic_global_init.cfg
        if init_steps is not None:
            for symlink, step in init_steps.items():
                self.add_step(step, symlink=symlink)

        forward_step = Forward(
            component=component,
            name='short',
            subdir=f'{base}/short',
            init_condition=init_condition,
            validate_vars=[
                'temperature',
                'salinity',
                'layerThickness',
                'normalVelocity',
            ],
        )
        forward_step.set_shared_config(config, link=config_filename)
        self.add_step(forward_step)
