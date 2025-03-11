from polaris.config import PolarisConfigParser as PolarisConfigParser
from polaris.ocean.tasks.internal_wave.default import Default as Default
from polaris.ocean.tasks.internal_wave.init import Init as Init
from polaris.ocean.tasks.internal_wave.rpe import Rpe as Rpe


def add_internal_wave_tasks(component):
    """
    Add tasks for different internal wave tests to the ocean component

    component : polaris.ocean.Ocean
        the ocean component that the tasks will be added to
    """
    config_filename = 'internal_wave.cfg'
    base_dir = 'planar/internal_wave'
    config = PolarisConfigParser(filepath=f'{base_dir}/{config_filename}')
    config.add_from_package('polaris.ocean.tasks.internal_wave',
                            config_filename)

    init = Init(component=component, indir=base_dir)
    init.set_shared_config(config, link=config_filename)

    for vadv_method in ['standard', 'vlr']:
        default = Default(component=component, indir=base_dir, init=init,
                          vadv_method=vadv_method)
        default.set_shared_config(config, link=config_filename)
        component.add_task(default)

        component.add_task(Rpe(component=component, indir=base_dir, init=init,
                               vadv_method=vadv_method, config=config))
