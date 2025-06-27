from polaris.config import PolarisConfigParser as PolarisConfigParser
from polaris.tasks.ocean.barotropic_channel.default import Default as Default


def add_barotropic_channel_tasks(component):
    """
    Add tasks for barotropic channel tests to the ocean component

    component : polaris.tasks.ocean.Ocean
        the ocean component that the tasks will be added to
    """

    group_name = 'barotropic_channel'
    config_filename = f'{group_name}.cfg'
    config = PolarisConfigParser(filepath=f'polaris.tasks.{config_filename}')
    config.add_from_package(
        f'polaris.tasks.ocean.{group_name}', config_filename
    )
    default = Default(component=component)
    default.set_shared_config(config, link=config_filename)
    component.add_task(default)
