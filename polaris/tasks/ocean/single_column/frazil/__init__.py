import numpy as np

from polaris import Task
from polaris.constants import get_constant
from polaris.ocean.eos import compute_ct_freezing
from polaris.ocean.model import OceanIOStep
from polaris.tasks.ocean.single_column.conservation_summary import (
    ConservationSummary,
)
from polaris.tasks.ocean.single_column.forward import Forward
from polaris.tasks.ocean.single_column.frazil.init import FrazilInit
from polaris.tasks.ocean.single_column.frazil.viz import FrazilViz


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

    def __init__(self, component, subdir, case, depth_limit=False):
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

        depth_limit : bool, optional
            Run one frazil-only melting timestep and check the depth limit.
        """
        name = 'melting_depth_limit' if depth_limit else case
        super().__init__(component=component, name=name, subdir=subdir)
        self.case = case

        self.config.add_from_package(
            'polaris.tasks.ocean.single_column', 'single_column.cfg'
        )
        self.config.add_from_package(
            'polaris.tasks.ocean.single_column.frazil', 'frazil.cfg'
        )
        if depth_limit:
            self.config.set(
                'single_column_frazil', 'temperature_lower_melting', '-3.0'
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
        time_step = self.config.getfloat('single_column', 'time_step')
        run_duration_steps = int(round(86400.0 / time_step))
        if run_duration_steps * time_step != 86400.0:
            raise ValueError(
                'The frazil run must contain an integer number '
                'of time steps in one day'
            )
        if depth_limit:
            run_duration_steps = 1
        frazil_conservation = self.case == 'freezing' or depth_limit
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
                task_package=(
                    'polaris.tasks.ocean.single_column.frazil.melting_short'
                    if depth_limit
                    else 'polaris.tasks.ocean.single_column.frazil'
                ),
                frazil_type=frazil_type,
                run_duration_steps=run_duration_steps,
                frazil_conservation=frazil_conservation,
            )
            if depth_limit:
                forward_step.add_model_config_options(
                    options={
                        'config_disable_vel_vmix': True,
                        'config_disable_tr_vmix': True,
                    },
                    config_model='ocean',
                )
            self.add_step(forward_step)
            self._frazil_type_steps[frazil_type] = forward_step
            comparisons[frazil_type] = f'../forward_{frazil_type}'
            forward_steps[forward_step.name] = forward_step.path
        self.conservation_summary = ConservationSummary(
            component=component,
            indir=subdir,
            forward_steps=forward_steps,
            frazil_diagnostics=(case == 'freezing'),
        )
        self.add_step(self.conservation_summary)
        if depth_limit:
            self.add_step(
                MeltingAnalysis(
                    component,
                    subdir,
                    init_step,
                    comparisons,
                    depth_limit=True,
                )
            )
        self.viz = FrazilViz(
            component=component,
            indir=subdir,
            init=init_step,
            comparisons=comparisons,
            mpas_ocean_frazil=True,
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
        self.config.add_from_package('polaris.ocean.eos', 'linear.cfg')
        for step in self._frazil_type_steps.values():
            step.frazil_conservation = True
        self.conservation_summary.frazil_diagnostics = True
        teos_step = self._frazil_type_steps.pop('teos', None)
        if teos_step is not None:
            self.remove_step(teos_step)
            self.conservation_summary.forward_steps.pop(teos_step.name, None)
            comparisons = dict(self.viz.comparisons)
            comparisons.pop('teos', None)
            if 'analysis' in self.steps:
                depth_limit = self.steps['analysis'].depth_limit
                self.remove_step(self.steps['analysis'])
                self.add_step(
                    MeltingAnalysis(
                        self.component,
                        self.subdir,
                        self.steps['init'],
                        comparisons,
                        depth_limit=depth_limit,
                    )
                )
            self.remove_step(self.viz)
            self.viz = FrazilViz(
                component=self.component,
                indir=self.subdir,
                init=self.steps['init'],
                comparisons=comparisons,
                mpas_ocean_frazil=True,
            )
            self.add_step(self.viz, run_by_default=False)


class MeltingAnalysis(OceanIOStep):
    """Check bottom-layer relaxation or frazil depth-limit enforcement."""

    def __init__(self, component, indir, init, comparisons, depth_limit=False):
        super().__init__(component=component, name='analysis', indir=indir)
        self.comparisons = dict(comparisons)
        self.depth_limit = depth_limit
        self.add_input_file(
            filename='init.nc', work_dir_target=f'{init.path}/init.nc'
        )
        for name, path in comparisons.items():
            self.add_input_file(
                filename=f'{name}.nc', target=f'{path}/output.nc'
            )

    def run(self):
        """Check isolated frazil warming or bottom-layer relaxation."""
        section = self.config['single_column_frazil']
        initial_minimum = section.getfloat('initial_supercooling_minimum')
        final_maximum = section.getfloat('final_supercooling_tolerance')
        if (
            not np.isfinite(initial_minimum)
            or not np.isfinite(final_maximum)
            or initial_minimum <= 0.0
            or final_maximum < 0.0
        ):
            raise ValueError('Invalid melting supercooling thresholds')
        with self.open_model_dataset('init.nc', config=self.config) as ds:
            initial_state = ds.isel(Time=0).load()
        if self.depth_limit:
            for name in self.comparisons:
                with self.open_model_dataset(
                    f'{name}.nc', config=self.config
                ) as ds:
                    self._check_depth_limit(
                        initial_state, ds.isel(Time=0), name
                    )
            return
        initial = float(np.min(self._bottom_supercooling(initial_state)))
        self.logger.info(f'Initial minimum supercooling: {initial:.6e} degC')
        if initial < initial_minimum:
            raise ValueError(
                f'Initial supercooling {initial:.6e} degC is below '
                f'{initial_minimum:.6e} degC'
            )
        for name in self.comparisons:
            with self.open_model_dataset(
                f'{name}.nc', config=self.config
            ) as ds:
                final = float(
                    np.max(abs(self._bottom_supercooling(ds.isel(Time=-1))))
                )
            self.logger.info(
                f'{name} final maximum freezing-point error: {final:.6e} degC'
            )
            if abs(final) > final_maximum:
                raise ValueError(
                    f'{name} final supercooling {final:.6e} degC exceeds '
                    f'{final_maximum:.6e} degC'
                )

    def _bottom_supercooling(self, ds):
        model = self.config.get('ocean', 'model')
        thickness = ds[
            'PseudoThickness' if model == 'omega' else 'layerThickness'
        ]
        depth = thickness.cumsum('nVertLevels') - 0.5 * thickness
        pressure = (
            depth
            * get_constant('seawater_density_reference')
            * get_constant('standard_acceleration_of_gravity')
        )
        freezing = compute_ct_freezing(
            self.config, ds.salinity, pressure=pressure
        )
        supercooling = (freezing - ds.temperature).isel(nVertLevels=-1).values
        if supercooling.size == 0 or not np.isfinite(supercooling).all():
            raise ValueError('Missing or nonfinite bottom-layer supercooling')
        return supercooling

    def _check_depth_limit(self, initial, final, name):
        depth = abs(initial.zMid)
        limit = self.config.getfloat('single_column_frazil', 'maximum_depth')
        pressure = (
            depth
            * get_constant('seawater_density_reference')
            * get_constant('standard_acceleration_of_gravity')
        )
        freezing = compute_ct_freezing(
            self.config, initial.salinity, pressure=pressure
        )
        supercooled = initial.temperature < freezing
        allowed = depth <= limit
        if not bool((supercooled & allowed).any()) or not bool(
            (supercooled & ~allowed).any()
        ):
            raise ValueError(
                'Depth-limit test needs supercooled water above and below '
                f'{limit} m'
            )
        warming = final.temperature - initial.temperature
        tolerance = 1.0e-10
        invalid = (
            ~np.isfinite(warming)
            | (supercooled & allowed & (warming <= tolerance))
            | (~allowed & (abs(warming) > tolerance))
        )
        if bool(invalid.any()):
            raise ValueError(
                f'{name}: frazil depth-limit check failed; '
                f'depth (m)={depth.values[invalid.values]}, '
                f'temperature change (degC)='
                f'{warming.values[invalid.values]}'
            )
        self.logger.info(f'{name}: frazil depth-limit check passed')
