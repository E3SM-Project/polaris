from polaris import Task
from polaris.config import PolarisConfigParser
from polaris.tasks.ocean.realistic_global.dynamic_adjustment.schedule import (
    load_schedule_stages,
)
from polaris.tasks.ocean.realistic_global.dynamic_adjustment.validate import (
    Validate,
)
from polaris.tasks.ocean.realistic_global.dynamic_adjustment.viz import (
    VizDynamicAdjustmentStep,
)
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

CONFIG_FILENAME = 'realistic_global_dynamic_adjustment.cfg'
CONFIG_PACKAGE = 'polaris.tasks.ocean.realistic_global.dynamic_adjustment'
FORWARD_CONFIG_FILENAME = 'realistic_global_forward.cfg'
FORWARD_CONFIG_PACKAGE = 'polaris.tasks.ocean.realistic_global.forward'
VALIDATE_VARS = [
    'temperature',
    'salinity',
    'layerThickness',
    'normalVelocity',
]


class RealisticGlobalDynamicAdjustment(Task):
    """
    A staged dynamic-adjustment run of the configured ocean model for a
    realistic global ocean simulation on one MPAS mesh.

    The task runs the shared ``realistic_global/init`` steps for the mesh, then
    a chain of ``Forward`` stages defined by a schedule YAML (``default.yaml``
    or ``<mesh_name>.yaml`` in this package), each restarting from the previous
    one.  A final ``Validate`` step checks the sequence for obvious failures.

    The stages are built once at construction from the built-in schedule (so
    ``polaris list`` shows a representative set) and rebuilt in ``configure``,
    so a user's setup-time config (including a ``schedule`` override) takes
    effect.  The number of stages is therefore fixed at setup time, not run
    time.

    Because each stage is a forward run, the task's config carries the
    ``[realistic_global_forward]`` options as well as its own, plus the
    per-mesh overrides from
    :py:mod:`polaris.tasks.ocean.realistic_global.mesh_configs`.

    Attributes
    ----------
    mesh_name : str
        The name of the MPAS mesh.

    base : str
        The task's base work-directory path, under which the stage and restart
        directories live.
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
        base = f'spherical/realistic_global/{mesh_name}/dynamic_adjustment'
        super().__init__(
            component=component,
            name='realistic_global_dynamic_adjustment',
            subdir=f'{base}/task',
        )
        self.mesh_name = mesh_name
        self.base = base

        # a stage is a forward run, so the task carries the forward run's
        # config options as well as its own; the per-mesh file comes last so
        # that its overrides win
        filepath = f'{component.name}/{base}/{CONFIG_FILENAME}'
        config = PolarisConfigParser(filepath=filepath)
        config.add_from_package(
            FORWARD_CONFIG_PACKAGE, FORWARD_CONFIG_FILENAME
        )
        config.add_from_package(CONFIG_PACKAGE, CONFIG_FILENAME)
        add_realistic_global_mesh_config(config=config, mesh_name=mesh_name)
        self.set_shared_config(config, link=CONFIG_FILENAME)

        self._setup_steps()

    def configure(self):
        """
        Rebuild the stages so a user's setup-time schedule or option overrides
        take effect.
        """
        super().configure()
        self._setup_steps()

    def _setup_steps(self):
        """
        Build the init steps, one forward step per schedule stage (chained by
        restart), and the validation step, replacing any existing steps.
        """
        component = self.component
        config = self.config
        mesh_name = self.mesh_name
        base = self.base

        # start fresh so a re-read schedule can add or remove stages
        for step in list(self.steps.values()):
            self.remove_step(step)

        init_steps, _ = get_realistic_init_steps(
            component=component, mesh_name=mesh_name, include_viz=False
        )
        for symlink, step in init_steps.items():
            self.add_step(step, symlink=symlink)

        init_step = init_steps['initial_state']
        min_res = min_res_for_mesh(mesh_name)
        approx_cell_count = estimate_ocean_cell_count(mesh_name)

        stages = load_schedule_stages(mesh_name, config)

        previous = None
        for stage in stages:
            forward_step = Forward(
                component=component,
                name=stage.name,
                subdir=f'{base}/{stage.name}',
                init_condition=StepInitialCondition(
                    init_step,
                    min_res=min_res,
                    approx_cell_count=approx_cell_count,
                    forcing_step=init_steps['forcing'],
                ),
                stage=stage,
                validate_vars=(
                    VALIDATE_VARS if stage.name == 'simulation' else None
                ),
            )
            forward_step.set_shared_config(config, link=CONFIG_FILENAME)
            if previous is not None:
                forward_step.add_dependency(previous, previous.name)
            self.add_step(forward_step)
            previous = forward_step

        validate_step = Validate(
            component=component, stages=stages, indir=base
        )
        validate_step.set_shared_config(config, link=CONFIG_FILENAME)
        self.add_step(validate_step)

        # the figure describes a completed adjustment, which is not what a
        # workflow that only wants the relaxed restart is asking about, so it
        # belongs to this standalone task rather than to the stages
        viz_step = VizDynamicAdjustmentStep(
            component=component, stages=stages, indir=base
        )
        viz_step.set_shared_config(config, link=CONFIG_FILENAME)
        self.add_step(viz_step)
