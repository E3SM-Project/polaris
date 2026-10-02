import os

from polaris import Task
from polaris.tasks.ocean.single_column.init import Init
from polaris.tasks.ocean.single_column.shortwave_pen.analysis import Analysis
from polaris.tasks.ocean.single_column.shortwave_pen.extinction import (
    Extinction,
)
from polaris.tasks.ocean.single_column.shortwave_pen.forward import (
    ShortwavePenForward,
)
from polaris.tasks.ocean.single_column.shortwave_pen.jerlov import (
    manizza_scale,
    omega_jerlov_equivalent,
)
from polaris.tasks.ocean.single_column.shortwave_pen.viz import Viz


class ShortwavePen(Task):
    """
    A single-column test of penetrating shortwave radiation over a range of
    Jerlov water types.  Every run is driven by the same constant, uniform
    incident surface shortwave flux for 3 hours, so the incident energy is
    identical and only the vertical distribution of the heating differs.

    Each water type gets a ``jerlov`` run, in which MPAS-Ocean's two-band
    scheme and Omega's three-band scheme are configured to absorb the flux
    identically.  Under Omega each water type additionally gets a ``manizza``
    run, whose red and blue bands take distinct extinction coefficients, to
    show what the third band changes.

    The constructor builds the Omega superset of steps so component
    configuration can detect the required ocean I/O and model support.  The
    steps are rebuilt for the selected ocean model in :py:meth:`configure`.
    """

    def __init__(self, component, indir):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this task belongs to

        indir : str
            The directory the task is in
        """
        name = 'shortwave_pen'
        subdir = os.path.join(indir, name)
        super().__init__(component=component, name=name, subdir=subdir)

        self.config.add_from_package('polaris.ocean.eos', 'linear.cfg')
        self.config.add_from_package(
            'polaris.tasks.ocean.single_column', 'single_column.cfg'
        )
        self.config.add_from_package(
            'polaris.tasks.ocean.single_column.shortwave_pen',
            'shortwave_pen.cfg',
        )

        self._setup_steps(model='omega')

    def configure(self):
        """
        Build the steps now that the ocean model and the water types to run
        are known
        """
        super().configure()
        model = self.config.get('ocean', 'model')
        self._setup_steps(model=model)

    def _setup_steps(self, model):
        """
        Add a forward step for each water type, along with the Omega-only
        Manizza runs and the extinction-coefficient steps they need

        Parameters
        ----------
        model : {'mpas-ocean', 'omega'}
            The ocean model to build steps for
        """
        config = self.config
        component = self.component
        subdir = self.subdir
        section = config['single_column_shortwave_pen']
        water_types = config.getlist(
            'single_column_shortwave_pen', 'water_types', dtype=int
        )
        coeff_red = section.getfloat('extinction_coeff_red')
        coeff_blue = section.getfloat('extinction_coeff_blue')

        for step in list(self.steps.values()):
            self.remove_step(step)

        init_step = Init(
            component,
            name='init',
            subdir=f'{subdir}/init',
            forcing_vars=['short_wave_heat_flux'],
        )
        self.add_step(init_step)

        validate_vars = ['temperature', 'salinity']
        forward_steps = dict()

        for water_type in water_types:
            _, jerlov_coeff = omega_jerlov_equivalent(water_type)
            scale = manizza_scale(water_type)
            coeffs = {
                'jerlov': (jerlov_coeff, jerlov_coeff),
                'manizza': (coeff_red * scale, coeff_blue * scale),
            }
            # only Omega has a third band to vary
            schemes = ['jerlov'] if model == 'mpas-ocean' else list(coeffs)

            for scheme in schemes:
                suffix = f'{scheme}_type{water_type}'
                red, blue = coeffs[scheme]
                extinction_step = Extinction(
                    component=component,
                    name=f'extinction_{suffix}',
                    subdir=f'{subdir}/extinction_{suffix}',
                    init=init_step,
                    extinction_coeff_red=red,
                    extinction_coeff_blue=blue,
                )
                # MPAS-Ocean gets its coefficients from the Jerlov table in
                # the model, so the forcing file would go unused
                if model == 'omega':
                    self.add_step(extinction_step)

                forward_step = ShortwavePenForward(
                    component=component,
                    init=init_step,
                    extinction=extinction_step,
                    name=f'forward_{suffix}',
                    indir=subdir,
                    water_type=water_type,
                    scheme=scheme,
                    ntasks=1,
                    min_tasks=1,
                    openmp_threads=1,
                    validate_vars=validate_vars,
                )
                self.add_step(forward_step)
                forward_steps[suffix] = forward_step

        self.add_step(
            Analysis(
                component=component,
                indir=subdir,
                init=init_step,
                water_types=water_types,
            )
        )
        self.add_step(
            Viz(
                component=component,
                indir=subdir,
                init=init_step,
                water_types=water_types,
                comparisons={
                    suffix: f'../forward_{suffix}' for suffix in forward_steps
                },
            )
        )
