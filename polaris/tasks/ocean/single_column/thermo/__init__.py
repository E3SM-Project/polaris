import os

from polaris import Task
from polaris.tasks.ocean.single_column.forward import Forward
from polaris.tasks.ocean.single_column.init import Init
from polaris.tasks.ocean.single_column.viz import Viz


class Thermo(Task):
    """
    The Thermo single-column test case creates the mesh and initial condition,
    then performs several short forward runs corresponding to each supported
    surface thermodynamic forcing variable.
    """

    def __init__(self, component, indir):
        """
        Create the test case
        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this task belongs to
        """
        group_name = 'single_column'
        name = 'thermo'
        subdir = os.path.join(indir, name)
        super().__init__(component=component, name=name, subdir=subdir)

        self.config.add_from_package('polaris.ocean.eos', 'linear.cfg')
        self.config.add_from_package(
            'polaris.tasks.ocean.single_column', f'{group_name}.cfg'
        )
        self.config.add_from_package(
            'polaris.tasks.ocean.single_column', 'stable_stratification.cfg'
        )
        self.config.add_from_package(
            'polaris.tasks.ocean.single_column', 'wind.cfg'
        )
        self.config.add_from_package(
            f'polaris.tasks.ocean.single_column.{name}', f'{name}.cfg'
        )

        validate_vars = [
            'temperature',
            'salinity',
            'layerThickness',
            'normalVelocity',
        ]
        # Only testing those with both MPAS-O and Omega support
        forcing_vars = [
            'latent_heat_flux',
            'sensible_heat_flux',
            'short_wave_heat_flux',
            'long_wave_heat_flux_up',
            'long_wave_heat_flux_down',
            'evaporation_flux',
            'snow_flux',
            'rain_flux',
            'river_runoff_flux',
            'ice_runoff_flux',
            'sea_ice_fresh_water_flux',
            'sea_ice_heat_flux',
            'sea_ice_salinity_flux',
        ]
        comparisons = dict()
        for forcing_var in forcing_vars:
            init_step = Init(
                component,
                name=f'init_{forcing_var}',
                subdir=f'column/init/{forcing_var}/stable',
                forcing_vars=[forcing_var],
            )
            self.add_step(init_step)

            forward_step = Forward(
                component=component,
                init=init_step,
                indir=self.subdir,
                name=f'forward_{forcing_var}',
                ntasks=1,
                min_tasks=1,
                openmp_threads=1,
                validate_vars=validate_vars,
                task_name=name,
            )
            self.add_step(forward_step)
            comparisons[f'{forcing_var}'] = f'../forward_{forcing_var}'
        self.add_step(
            Viz(
                component=component,
                indir=self.subdir,
                init=init_step,
                comparisons=comparisons,
            ),
            run_by_default=False,
        )
