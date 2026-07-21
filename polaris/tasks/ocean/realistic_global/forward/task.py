from polaris import Task
from polaris.config import PolarisConfigParser
from polaris.tasks.ocean.realistic_global.forward.forward import Forward
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


class RealisticGlobalForward(Task):
    """
    A simple forward run of the configured ocean model for a realistic global
    ocean simulation on one MPAS mesh.

    The task runs the shared ``realistic_global/init`` steps for the mesh to
    produce the initial condition, then a single short :py:class:`.Forward`
    run (the ``short`` step, a brief smoke test) whose duration and cadence
    come from the ``[realistic_global_forward]`` config section.  The target
    model is resolved from ``[ocean] model`` during component setup.
    """

    def __init__(self, component, mesh_name):
        """
        Create the task.

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the task belongs to.

        mesh_name : str
            The name of the MPAS mesh (e.g. ``'icos240km'``).
        """
        base = f'spherical/realistic_global/{mesh_name}/forward'
        super().__init__(
            component=component,
            name='realistic_global_forward',
            subdir=f'{base}/task',
        )

        # the shared init steps carry their own realistic_global_init.cfg
        init_steps, _ = get_realistic_init_steps(
            component=component, mesh_name=mesh_name, include_viz=False
        )

        config_filename = 'realistic_global_forward.cfg'
        filepath = f'{component.name}/{base}/{config_filename}'
        config = PolarisConfigParser(filepath=filepath)
        config.add_from_package(
            'polaris.tasks.ocean.realistic_global.forward', config_filename
        )
        add_realistic_global_mesh_config(config=config, mesh_name=mesh_name)
        self.set_shared_config(config, link=config_filename)

        for symlink, step in init_steps.items():
            self.add_step(step, symlink=symlink)

        init_step = init_steps['initial_state']
        min_res = min_res_for_mesh(mesh_name)
        approx_cell_count = estimate_ocean_cell_count(mesh_name)
        forward_step = Forward(
            component=component,
            name='short',
            subdir=f'{base}/short',
            init_condition=StepInitialCondition(
                init_step,
                min_res=min_res,
                approx_cell_count=approx_cell_count,
            ),
            validate_vars=[
                'temperature',
                'salinity',
                'layerThickness',
                'normalVelocity',
            ],
        )
        forward_step.set_shared_config(config, link=config_filename)
        self.add_step(forward_step)
