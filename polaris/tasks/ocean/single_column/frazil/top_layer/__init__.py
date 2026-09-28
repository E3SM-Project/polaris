from polaris import Task
from polaris.tasks.ocean.single_column.conservation_summary import (
    ConservationSummary,
)
from polaris.tasks.ocean.single_column.forward import Forward
from polaris.tasks.ocean.single_column.frazil.init import FrazilInit
from polaris.tasks.ocean.single_column.frazil.top_layer.viz import TopLayerViz

TIME_INTEGRATORS = (
    'RK4',
    'Forward-Backward',
    'RungeKutta2',
    'SplitExplicitRK2',
    'UnsplitRK2',
)


class FrazilTopLayer(Task):
    """
    A single-column frazil test case on a three-layer, 10 m resolution column
    initialized at the local freezing point.  All tendencies are disabled
    except the surface tracer forcing and the frazil tendency, so the change
    in the heat content of the top layer is set entirely by the applied
    surface heat flux and by frazil formation.  Omega runs each of its five
    time integrators with both frazil algorithms (``'FixedProperty'`` and
    ``'teos'``).  MPAS-Ocean retains only RK4 with ``'FixedProperty'``.
    """

    def __init__(self, component, subdir):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this task belongs to

        subdir : str
            The directory the task is in
        """
        super().__init__(
            component=component, name='freezing_topLayer', subdir=subdir
        )

        self.config.add_from_package(
            'polaris.tasks.ocean.single_column', 'single_column.cfg'
        )
        self.config.add_from_package(
            'polaris.tasks.ocean.single_column.frazil', 'frazil.cfg'
        )
        self.config.add_from_package(
            'polaris.tasks.ocean.single_column.frazil.top_layer',
            'top_layer.cfg',
        )
        init_step = FrazilInit(
            component=component,
            subdir=f'{subdir}/init',
            case='freezing',
            at_freezing=True,
        )
        self.add_step(init_step)

        time_step = self.config.getfloat('single_column', 'time_step')
        run_duration_steps = int(round(86400.0 / time_step))
        if run_duration_steps * time_step != 86400.0:
            raise ValueError(
                'The frazil top-layer run must contain an integer number of '
                'time steps in one day'
            )

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
                    task_name='frazil_top_layer',
                    task_package=(
                        'polaris.tasks.ocean.single_column.frazil.top_layer'
                    ),
                    frazil_type=frazil_type,
                    run_duration_steps=run_duration_steps,
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
        self.viz = TopLayerViz(
            component=component,
            indir=subdir,
            init=init_step,
            comparisons=comparisons,
        )
        self.add_step(self.viz, run_by_default=False)

    def configure(self):
        """
        Keep the original RK4 FixedProperty case for MPAS-Ocean.
        """
        model = self.config.get('ocean', 'model')
        if model != 'mpas-ocean':
            return
        for (time_integrator, frazil_type), step in list(
            self._frazil_type_steps.items()
        ):
            if (time_integrator, frazil_type) == ('RK4', 'FixedProperty'):
                continue
            self.remove_step(step)
            self.conservation_summary.forward_steps.pop(step.name, None)
            self.viz.comparisons.pop(f'{time_integrator} {frazil_type}', None)
            del self._frazil_type_steps[time_integrator, frazil_type]
