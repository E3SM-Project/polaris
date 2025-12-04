from polaris.config import PolarisConfigParser as PolarisConfigParser
from polaris.tasks.ocean.seamount.default import Default as Default
from polaris.tasks.ocean.seamount.init import Init as Init


def add_seamount_tasks(component):
    """
    Add a task following the seamount test case

    component : polaris.ocean.Ocean
        the ocean component that the task will be added to
    """
    indir = 'planar/seamount'
    config_filename = 'seamount.cfg'
    config = PolarisConfigParser(filepath=f'{indir}/{config_filename}')
    config.add_from_package('polaris.tasks.ocean.seamount', config_filename)

    init_step = Init(component=component, name='init', indir=indir)
    init_step.set_shared_config(config, link=config_filename)

    default = Default(component=component, indir=indir, init=init_step)
    default.set_shared_config(config, link=config_filename)
    component.add_task(default)
