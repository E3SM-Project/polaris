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
from polaris.tasks.ocean.single_column.viz import Viz


class ShortwavePen(Task):
    """
    A single-column test that compares Omega's penetrating-shortwave-
    radiation scheme against the default behavior of absorbing all
    shortwave heating in the surface layer.  Both runs are driven by the
    same constant, uniform incident surface shortwave flux for 3 hours;
    the column-integrated heating should be identical between the two runs
    while the vertical distribution of the heating, and thus the resulting
    temperature profile and column potential energy, should differ.

    This task requires Omega; MPAS-Ocean does not implement a penetrating-
    shortwave-radiation scheme.
    """

    def __init__(self, component, indir):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this task belongs to
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

        init_step = Init(
            component,
            name='init',
            subdir=f'{subdir}/init',
            forcing_vars=['short_wave_heat_flux'],
        )
        self.add_step(init_step)

        extinction_step = Extinction(
            component=component,
            subdir=f'{subdir}/extinction',
            init=init_step,
        )
        self.add_step(extinction_step)

        validate_vars = ['temperature', 'salinity']

        constant_step = ShortwavePenForward(
            component=component,
            init=init_step,
            extinction=extinction_step,
            name='forward_constant',
            indir=self.subdir,
            use_penetrating_sw=False,
            ntasks=1,
            min_tasks=1,
            openmp_threads=1,
            validate_vars=validate_vars,
        )
        self.add_step(constant_step)

        pen_step = ShortwavePenForward(
            component=component,
            init=init_step,
            extinction=extinction_step,
            name='forward_pen',
            indir=self.subdir,
            use_penetrating_sw=True,
            ntasks=1,
            min_tasks=1,
            openmp_threads=1,
            validate_vars=validate_vars,
        )
        self.add_step(pen_step)

        self.add_step(
            Analysis(
                component=component,
                indir=self.subdir,
                init=init_step,
                constant_step=constant_step,
                pen_step=pen_step,
            )
        )
        self.add_step(
            Viz(
                component=component,
                indir=self.subdir,
                init=init_step,
                comparisons={
                    'constant': '../forward_constant',
                    'pen': '../forward_pen',
                },
                variables={'temperature': 'degC'},
                plot_diff=True,
            ),
        )
