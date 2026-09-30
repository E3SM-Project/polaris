from polaris import Task
from polaris.tasks.ocean.single_column.conservation_summary import (
    ConservationSummary,
)
from polaris.tasks.ocean.single_column.forward import Forward
from polaris.tasks.ocean.single_column.frazil.init import FrazilInit
from polaris.tasks.ocean.single_column.frazil.melt_short.viz import (
    MeltShortViz,
)

TIME_INTEGRATORS = (
    'RK4',
    'RungeKutta2',
    'SplitExplicitRK2',
    'UnsplitRK2',
)

RUN_DURATION_STEPS = 4


class FrazilMeltShort(Task):
    """
    A two-layer single-column frazil test with a warm top layer over a
    supercooled bottom layer and no surface forcing.  All tendencies are
    disabled except frazil, so the evolution of both layers is set entirely
    by frazil formation and melting.  Omega runs each of its time
    integrators with both frazil algorithms (``'FixedProperty'`` and
    ``'teos'``).  MPAS-Ocean retains only RK4 with ``'FixedProperty'``.
    """

    def __init__(self, component, subdir, name='melt_short'):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this task belongs to

        subdir : str
            The directory the task is in

        name : str, optional
            The task name
        """
        super().__init__(component=component, name=name, subdir=subdir)

        self.config.add_from_package(
            'polaris.tasks.ocean.single_column', 'single_column.cfg'
        )
        self.config.add_from_package(
            'polaris.tasks.ocean.single_column.frazil', 'frazil.cfg'
        )
        self.config.add_from_package(
            'polaris.tasks.ocean.single_column.frazil.melt_short',
            'melt_short.cfg',
        )
        init_step = FrazilInit(
            component=component,
            subdir=f'{subdir}/init',
            case='melt_short',
        )
        self.add_step(init_step)

        validate_vars = [
            'temperature',
            'salinity',
            'layerThickness',
            'normalVelocity',
        ]
        comparisons = dict()
        forward_steps = dict()
        self._frazil_type_steps = dict()
        for time_integrator in TIME_INTEGRATORS:
            for frazil_type in ('FixedProperty', 'teos'):
                forward_step = Forward(
                    component=component,
                    init=init_step,
                    indir=subdir,
                    name=f'forward_{frazil_type}',
                    ntasks=1,
                    min_tasks=1,
                    openmp_threads=1,
                    validate_vars=validate_vars,
                    task_name='frazil_melt_short',
                    task_package=(
                        'polaris.tasks.ocean.single_column.frazil.melt_short'
                    ),
                    frazil_type=frazil_type,
                    run_duration_steps=RUN_DURATION_STEPS,
                    frazil_conservation=True,
                    time_integrator=time_integrator,
                )
                self.add_step(forward_step)
                self._frazil_type_steps[time_integrator, frazil_type] = (
                    forward_step
                )
                comparisons[f'{time_integrator} {frazil_type}'] = (
                    f'../{forward_step.name}'
                )
                forward_steps[forward_step.name] = forward_step.path
        self.conservation_summary = ConservationSummary(
            component=component,
            indir=subdir,
            forward_steps=forward_steps,
            frazil_diagnostics=True,
        )
        self.add_step(self.conservation_summary)
        self.viz = MeltShortViz(
            component=component,
            indir=subdir,
            init=init_step,
            comparisons=comparisons,
        )
        self.add_step(self.viz, run_by_default=False)

    def configure(self):
        """
        Keep only the RK4 ``'FixedProperty'`` forward step if the ocean model
        is MPAS-Ocean, which supports neither the other time integrators nor
        the ``'teos'`` algorithm
        """
        model = self.config.get('ocean', 'model')
        if model != 'mpas-ocean':
            return
        for key, step in list(self._frazil_type_steps.items()):
            if key == ('RK4', 'FixedProperty'):
                continue
            self._frazil_type_steps.pop(key)
            self.remove_step(step)
            self.conservation_summary.forward_steps.pop(step.name, None)
            self.viz.comparisons.pop(f'{key[0]} {key[1]}', None)
