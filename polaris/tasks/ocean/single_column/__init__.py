from polaris.config import PolarisConfigParser as PolarisConfigParser
from polaris.tasks.ocean.single_column.ekman import Ekman as Ekman
from polaris.tasks.ocean.single_column.ideal_age import IdealAge as IdealAge
from polaris.tasks.ocean.single_column.inertial import Inertial as Inertial
from polaris.tasks.ocean.single_column.init import Init
from polaris.tasks.ocean.single_column.vmix import VMix as VMix


def add_single_column_tasks(component):
    """
    Add tasks for various single-column tests

    component : polaris.tasks.ocean.Ocean
        the ocean component that the tasks will be added to
    """
    group_name = 'single_column'

    name = 'vmix_stable'
    forcing = ['wind']
    forcing_dir = '_'.join(forcing) if forcing else 'no_forcing'
    filepath = f'{component.name}/{group_name}/{name}/{name}.cfg'
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
        subdir=f'{group_name}/{forcing_dir}/init_stable',
        config=config,
        config_filename=f'{name}.cfg',
    )
    component.add_task(
        VMix(
            component=component,
            config=config,
            name=name,
            init=init_step,
            indir=group_name,
        )
    )

    name = 'vmix_unstable'
    forcing = []
    forcing_dir = '_'.join(forcing) if forcing else 'no_forcing'
    filepath = f'{component.name}/{group_name}/{name}/{name}.cfg'
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
        subdir=f'{group_name}/{forcing_dir}/init_unstable',
        config=config,
        config_filename=f'{name}.cfg',
    )
    component.add_task(
        VMix(
            component=component,
            config=config,
            name=name,
            init=init_step,
            indir=group_name,
        )
    )

    forcing = ['wind']
    name = 'ekman'
    filepath = f'{component.name}/{group_name}/{name}/{name}.cfg'
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
        subdir=f'{group_name}/{forcing_name}/init',
        config=config,
        config_filename=f'{name}.cfg',
    )
    component.add_task(
        Ekman(
            component=component,
            config=config,
            init=init_step,
            indir=group_name,
        )
    )

    name = 'ideal_age'
    forcing = ['evap']
    forcing_dir = '_'.join(forcing) if forcing else 'no_forcing'
    filepath = f'{component.name}/{group_name}/{name}/{name}.cfg'
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
        subdir=f'{group_name}/{forcing_dir}/init_stable',
        config=config,
        config_filename=f'{name}.cfg',
    )
    component.add_task(
        IdealAge(
            component=component,
            init=init_step,
            config=config,
            indir=group_name,
        )
    )

    name = 'inertial'
    forcing = []
    forcing_dir = '_'.join(forcing) if forcing else 'no_forcing'
    filepath = f'{component.name}/{group_name}/{name}/{name}.cfg'
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
        subdir=f'{group_name}/{forcing_dir}/init_stable',
        config=config,
        config_filename=f'{name}.cfg',
    )
    component.add_task(
        Inertial(
            component=component,
            init=init_step,
            config=config,
            indir=group_name,
        )
    )
