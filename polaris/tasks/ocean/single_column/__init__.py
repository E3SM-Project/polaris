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
    forcing = ['wind', 'evap']
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
        'polaris.tasks.ocean.single_column', 'stable_stratification.cfg'
    )
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

    forcing = ['wind']
    name = 'ekman'
    filepath = f'{component.name}/column/{name}/{name}.cfg'
    config = PolarisConfigParser(filepath=filepath)
    config.add_from_package(
        'polaris.tasks.ocean.single_column', f'{group_name}.cfg'
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
    forcing = ['evap']
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
        'polaris.tasks.ocean.single_column', 'stable_stratification.cfg'
    )
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
        'polaris.tasks.ocean.single_column', 'stable_stratification.cfg'
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
        'kpp_wind': (['wind'], ['van_roekel_wnf']),
        # matches Van Roekel et al. (2018) Table 3, FC (free convection)
        'kpp_convection_cooling': (['cooling'], ['van_roekel_fc']),
        # matches Van Roekel et al. (2018) Table 3, CEW (cooling,
        # evaporation, and wind)
        'kpp_combined': (['wind', 'cooling'], ['van_roekel_cew']),
        'kpp_non_local_flux_suppression': (['evap'], []),
        'kpp_langmuir': (['wind', 'cooling', 'langmuir'], []),
        'kpp_sea_ice': (['wind', 'sea_ice'], []),
        'kpp_convection_evaporation': (['fce'], ['fce']),
        'kpp_cooling_with_mixedlayer': (['van_roekel_cooling'], ['fcml']),
        'kpp_strong_convection_cooling': ([], ['catke_strong_cooling']),
    }
    for name, (forcing, profile_configs) in kpp_regimes.items():
        forcing_dir = '_'.join(forcing)
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
            'polaris.tasks.ocean.single_column', 'stable_stratification.cfg'
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
            subdir=f'column/init/kpp/{forcing_dir}/stable',
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
