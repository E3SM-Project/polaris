from polaris.config import PolarisConfigParser as PolarisConfigParser
from polaris.tasks.ocean.single_column.ekman import Ekman as Ekman
from polaris.tasks.ocean.single_column.ideal_age import IdealAge as IdealAge
from polaris.tasks.ocean.single_column.inertial import Inertial as Inertial
from polaris.tasks.ocean.single_column.init import Init
from polaris.tasks.ocean.single_column.kpp_regimes import (
    KPPRegimes as KPPRegimes,
)
from polaris.tasks.ocean.single_column.thermo import Thermo as Thermo
from polaris.tasks.ocean.single_column.vmix import VMix as VMix


def add_single_column_tasks(component):
    """
    Add tasks for various single-column tests

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        the ocean component that the tasks will be added to
    """
    group_name = 'single_column'

    name = 'vmix_stable'
    forcing = ['wind_stress', 'evap_strong']
    forcing_dir = '_'.join(forcing) if forcing else 'no_forcing'
    filepath = f'{component.name}/column/{name}/{name}.cfg'
    config = PolarisConfigParser(filepath=filepath)
    config.add_from_package(
        'polaris.tasks.ocean.single_column', f'{group_name}.cfg'
    )
    config.add_from_package(
        'polaris.tasks.ocean.single_column',
        'neutral_temperature_salinity.cfg',
    )
    for forcing_name in forcing:
        config.add_from_package(
            'polaris.tasks.ocean.single_column', f'{forcing_name}.cfg'
        )
    config.add_from_package(
        'polaris.tasks.ocean.single_column',
        'stable_temperature_strong.cfg',
    )
    config.add_from_package('polaris.ocean.eos', 'linear.cfg')
    init_step = component.get_or_create_shared_step(
        step_cls=Init,
        subdir=f'column/init/{forcing_dir}/stable',
        config=config,
        config_filename=f'{name}.cfg',
    )
    component.add_task(
        VMix(
            component=component,
            config=config,
            name=name,
            init=init_step,
            indir='column',
        )
    )

    name = 'vmix_unstable'
    forcing = []
    forcing_dir = '_'.join(forcing) if forcing else 'no_forcing'
    filepath = f'{component.name}/column/{name}/{name}.cfg'
    config = PolarisConfigParser(filepath=filepath)
    config.add_from_package(
        'polaris.tasks.ocean.single_column', f'{group_name}.cfg'
    )
    config.add_from_package(
        'polaris.tasks.ocean.single_column',
        'neutral_temperature_salinity.cfg',
    )
    for forcing_name in forcing:
        config.add_from_package(
            'polaris.tasks.ocean.single_column', f'{forcing_name}.cfg'
        )
    config.add_from_package(
        'polaris.tasks.ocean.single_column', 'unstable_stratification.cfg'
    )
    init_step = component.get_or_create_shared_step(
        step_cls=Init,
        subdir=f'column/init/{forcing_dir}/unstable',
        config=config,
        config_filename=f'{name}.cfg',
    )
    component.add_task(
        VMix(
            component=component,
            config=config,
            name=name,
            init=init_step,
            indir='column',
        )
    )

    forcing = ['wind_stress']
    name = 'ekman'
    filepath = f'{component.name}/column/{name}/{name}.cfg'
    config = PolarisConfigParser(filepath=filepath)
    config.add_from_package(
        'polaris.tasks.ocean.single_column', f'{group_name}.cfg'
    )
    config.add_from_package(
        'polaris.tasks.ocean.single_column',
        'neutral_temperature_salinity.cfg',
    )
    for forcing_name in forcing:
        config.add_from_package(
            'polaris.tasks.ocean.single_column', f'{forcing_name}.cfg'
        )
    init_step = component.get_or_create_shared_step(
        step_cls=Init,
        subdir=f'column/init/{forcing_name}/neutral',
        config=config,
        config_filename=f'{name}.cfg',
    )
    component.add_task(
        Ekman(
            component=component,
            config=config,
            init=init_step,
            indir='column',
        )
    )

    name = 'ideal_age'
    forcing = ['evap_strong']
    forcing_dir = '_'.join(forcing) if forcing else 'no_forcing'
    filepath = f'{component.name}/column/{name}/{name}.cfg'
    config = PolarisConfigParser(filepath=filepath)
    config.add_from_package(
        'polaris.tasks.ocean.single_column', f'{group_name}.cfg'
    )
    config.add_from_package(
        'polaris.tasks.ocean.single_column',
        'neutral_temperature_salinity.cfg',
    )
    for forcing_name in forcing:
        config.add_from_package(
            'polaris.tasks.ocean.single_column', f'{forcing_name}.cfg'
        )
    config.add_from_package(
        'polaris.tasks.ocean.single_column',
        'stable_temperature_strong.cfg',
    )
    config.add_from_package('polaris.ocean.eos', 'linear.cfg')
    init_step = component.get_or_create_shared_step(
        step_cls=Init,
        subdir=f'column/init/{forcing_dir}/stable',
        config=config,
        config_filename=f'{name}.cfg',
    )
    component.add_task(
        IdealAge(
            component=component,
            init=init_step,
            config=config,
            indir='column',
        )
    )

    name = 'inertial'
    forcing = []
    forcing_dir = '_'.join(forcing) if forcing else 'no_forcing'
    filepath = f'{component.name}/column/{name}/{name}.cfg'
    config = PolarisConfigParser(filepath=filepath)
    config.add_from_package(
        'polaris.tasks.ocean.single_column', f'{group_name}.cfg'
    )
    for forcing_name in forcing:
        config.add_from_package(
            'polaris.tasks.ocean.single_column', f'{forcing_name}.cfg'
        )
    config.add_from_package(
        'polaris.tasks.ocean.single_column',
        'stable_temperature_strong.cfg',
    )
    init_step = component.get_or_create_shared_step(
        step_cls=Init,
        subdir=f'column/init/{forcing_dir}/stable',
        config=config,
        config_filename=f'{name}.cfg',
    )
    component.add_task(
        Inertial(
            component=component,
            init=init_step,
            config=config,
            indir='column',
        )
    )

    component.add_task(
        Thermo(
            component=component,
            indir='column',
        )
    )

    kpp_regimes = {
        # matches Van Roekel et al. (2018) Table 3, WNF (wind without
        # Coriolis)
        'kpp_wind': (['wind_stress'], ['no_coriolis']),
        # matches Van Roekel et al. (2018) Table 3, FC (free convection)
        'kpp_convection_cooling': (
            ['sensible_heat_cooling'],
            ['stable_temperature_weak'],
        ),
        # matches Van Roekel et al. (2018) Table 3, CEW (cooling,
        # evaporation, and wind)
        'kpp_combined': (
            ['wind_stress', 'sensible_heat_cooling', 'evap_weak'],
            ['stable_temperature_weak'],
        ),
        'kpp_non_local_flux_suppression': (
            ['evap_strong'],
            ['stable_temperature_strong'],
        ),
        'kpp_langmuir': (
            [
                'wind_stress',
                'wind_speed',
                'latent_heat_cooling',
                'sensible_heat_cooling',
            ],
            ['stable_temperature_strong'],
        ),
        'kpp_sea_ice': (
            ['wind_stress', 'sea_ice'],
            ['stable_temperature_strong'],
        ),
        'kpp_convection_evaporation': (
            ['evap_weak'],
            ['stable_salinity_weak'],
        ),
        'kpp_cooling_with_mixedlayer': (
            ['sensible_heat_cooling'],
            ['mixed_layer_stable_temperature_salinity'],
        ),
        'kpp_strong_convection_cooling': (
            ['sensible_heat_cooling_strong'],
            ['stable_temperature_weak'],
        ),
    }
    for name, (forcing, profile_configs) in kpp_regimes.items():
        forcing_dir = '_'.join(forcing)
        filepath = f'{component.name}/column/{name}/{name}.cfg'
        config = PolarisConfigParser(filepath=filepath)
        config.add_from_package(
            'polaris.tasks.ocean.single_column', f'{group_name}.cfg'
        )
        config.add_from_package(
            'polaris.tasks.ocean.single_column',
            'neutral_temperature_salinity.cfg',
        )
        for forcing_name in forcing:
            config.add_from_package(
                'polaris.tasks.ocean.single_column', f'{forcing_name}.cfg'
            )
        config.add_from_package(
            'polaris.tasks.ocean.single_column',
            'stable_temperature_strong.cfg',
        )
        for profile_config in profile_configs:
            config.add_from_package(
                'polaris.tasks.ocean.single_column', f'{profile_config}.cfg'
            )
        init_step = component.get_or_create_shared_step(
            step_cls=Init,
            # "kpp/" avoids colliding with other tasks' shared init steps
            # that happen to use the same forcing combo (e.g. ideal_age
            # also uses evap+stable), which would silently reuse the wrong
            # config (missing eos_linear.cfg) via get_or_create_shared_step
            subdir=f'column/init/{forcing_dir}/stable',
            config=config,
            config_filename=f'{name}.cfg',
        )
        component.add_task(
            KPPRegimes(
                component=component,
                config=config,
                init=init_step,
                indir='column',
                name=name,
            )
        )
