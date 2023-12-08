from polaris.config import PolarisConfigParser
from polaris.ocean.resolution import resolution_to_subdir
from polaris.ocean.tasks.ice_shelf_2d.default import Default
from polaris.ocean.tasks.ice_shelf_2d.init import Init


def add_ice_shelf_2d_tasks(component):
    """
    Add tasks for different ice shelf 2-d tests to the ocean component

    component : polaris.ocean.Ocean
        the ocean component that the tasks will be added to
    """
    # TODO add vertical coordinate
    # TODO add restart test
    for resolution in [5., 2.]:
        resdir = resolution_to_subdir(resolution)
        resdir = f'planar/ice_shelf_2d/{resdir}'

        config_filename = 'ice_shelf_2d.cfg'
        config = PolarisConfigParser(filepath=f'{resdir}/{config_filename}')
        config.add_from_package('polaris.ocean.tasks.ice_shelf_2d',
                                config_filename)

        init = Init(component=component, resolution=resolution, indir=resdir)
        init.set_shared_config(config, link=config_filename)

        default = Default(component=component, resolution=resolution,
                          indir=resdir, init=init, config=config)
        default.set_shared_config(config, link=config_filename)
        component.add_task(default)

        default = Default(component=component, resolution=resolution,
                          indir=resdir, init=init, config=config,
                          include_viz=True)
        default.set_shared_config(config, link=config_filename)
        component.add_task(default)

        default = Default(component=component, resolution=resolution,
                          indir=resdir, init=init, config=config,
                          include_restart=True)
        default.set_shared_config(config, link=config_filename)
        component.add_task(default)
