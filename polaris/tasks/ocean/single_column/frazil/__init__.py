from polaris import Task
from polaris.tasks.ocean.single_column.conservation_summary import (
    ConservationSummary,
)
from polaris.tasks.ocean.single_column.forward import Forward
from polaris.tasks.ocean.single_column.frazil.init import FrazilInit
from polaris.tasks.ocean.single_column.viz import Viz


class Frazil(Task):
    """
    A single-column frazil test case that creates the mesh and initial
    condition for a given melting/freezing case, then performs a forward
    run for each frazil algorithm (``'FixedProperty'`` and ``'teos'``).
    MPAS-Ocean only supports ``'FixedProperty'``, so the ``'teos'`` forward
    step is removed from the task in :py:meth:`configure()` when the ocean
    model is MPAS-Ocean.

    Attributes
    ----------
    case : str
        The initial condition/forcing case, either ``'melting'`` or
        ``'freezing'``
    """

    def __init__(self, component, subdir, case):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this task belongs to

        subdir : str
            The directory the task is in

        case : str
            The initial condition/forcing case, either ``'melting'`` or
            ``'freezing'``
        """
        name = case
        super().__init__(component=component, name=name, subdir=subdir)
        self.case = case

        self.config.add_from_package(
            'polaris.tasks.ocean.single_column', 'single_column.cfg'
        )
        self.config.add_from_package(
            'polaris.tasks.ocean.single_column.frazil', 'frazil.cfg'
        )
        init_step = FrazilInit(
            component=component,
            subdir=f'{subdir}/init',
            case=case,
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
                task_name='frazil',
                task_package='polaris.tasks.ocean.single_column.frazil',
                frazil_type=frazil_type,
            )
            self.add_step(forward_step)
            self._frazil_type_steps[frazil_type] = forward_step
            comparisons[frazil_type] = f'../forward_{frazil_type}'
            forward_steps[forward_step.name] = forward_step.path
        self.conservation_summary = ConservationSummary(
            component=component,
            indir=subdir,
            forward_steps=forward_steps,
        )
        self.add_step(self.conservation_summary)
        self.viz = Viz(
            component=component,
            indir=subdir,
            init=init_step,
            comparisons=comparisons,
        )
        self.add_step(
            self.viz,
            run_by_default=False,
        )

    def configure(self):
        """
        Remove the ``teos`` forward step, and the corresponding entries in
        the conservation summary and viz comparisons, if the ocean model is
        MPAS-Ocean, which only supports the ``'FixedProperty'`` algorithm
        """
        model = self.config.get('ocean', 'model')
        if model != 'mpas-ocean':
            return
        teos_step = self._frazil_type_steps.pop('teos', None)
        if teos_step is not None:
            self.remove_step(teos_step)
            self.conservation_summary.forward_steps.pop(teos_step.name, None)
        self.viz.comparisons.pop('teos', None)
