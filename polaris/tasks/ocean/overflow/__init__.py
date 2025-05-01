from polaris.config import PolarisConfigParser as PolarisConfigParser
from polaris.tasks.ocean.overflow.default import Default as Default
from polaris.tasks.ocean.overflow.init import Init as Init
from polaris.tasks.ocean.overflow.rpe import Rpe as Rpe


def add_overflow_tasks(component):
    """
    Add a task following the overflow test case of Petersen et al. (2015)
    doi:10.1016/j.ocemod.2014.12.004

    component : polaris.ocean.Ocean
        the ocean component that the task will be added to
    """
    indir = 'planar/overflow'
    config_filename = 'overflow.cfg'
    config = PolarisConfigParser(filepath=f'{indir}/{config_filename}')
    config.add_from_package('polaris.tasks.ocean.overflow', config_filename)

    init_step = Init(component=component, name='init', indir=indir)
    init_step.set_shared_config(config, link=config_filename)

    default = Default(component=component, indir=indir, init=init_step)
    default.set_shared_config(config, link=config_filename)
    component.add_task(default)

    component.add_task(
        Rpe(
            component=component,
            indir=indir,
            init=init_step,
            config=config,
        )
    )
