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
    for resolution in [5., 2.]:
        resdir = resolution_to_subdir(resolution)
        for coord_type in ['z-star', 'z-level']:
            basedir = f'planar/ice_shelf_2d/{resdir}/{coord_type}'

            config_filename = 'ice_shelf_2d.cfg'
            config = PolarisConfigParser(
                filepath=f'{basedir}/{config_filename}')
            config.add_from_package('polaris.ocean.ice_shelf',
                                    'ssh_adjustment.cfg')
            config.add_from_package('polaris.ocean.tasks.ice_shelf_2d',
                                    config_filename)
            config.set('vertical_grid', 'coord_type', coord_type)

            init = Init(component=component, resolution=resolution,
                        indir=basedir)
            init.set_shared_config(config, link=config_filename)

            default = Default(component=component, resolution=resolution,
                              indir=basedir, init=init, config=config)
            default.set_shared_config(config, link=config_filename)
            component.add_task(default)

            default = Default(component=component, resolution=resolution,
                              indir=basedir, init=init, config=config,
                              include_viz=True)
            default.set_shared_config(config, link=config_filename)
            component.add_task(default)

            default = Default(component=component, resolution=resolution,
                              indir=basedir, init=init, config=config,
                              include_restart=True)
            default.set_shared_config(config, link=config_filename)
            component.add_task(default)

            default = Default(component=component, resolution=resolution,
                              indir=basedir, init=init, config=config,
                              include_tides=True)
            default.set_shared_config(config, link=config_filename)
            component.add_task(default)

        # The only test case that makes sense with the single_layer coordinate
        # type is the one with barotropic tidal_forcing
        for coord_type in ['single_layer']:
            basedir = f'planar/ice_shelf_2d/{resdir}/{coord_type}'

            config_filename = 'ice_shelf_2d.cfg'
            config = PolarisConfigParser(
                filepath=f'{basedir}/{config_filename}')
            config.add_from_package('polaris.ocean.ice_shelf',
                                    'ssh_adjustment.cfg')
            config.add_from_package('polaris.ocean.tasks.ice_shelf_2d',
                                    config_filename)
            config.set('vertical_grid', 'coord_type', 'z-level')
            config.set('vertical_grid', 'vert_levels', '1')
            config.set('vertical_grid', 'partial_cell_type', 'None')

            init = Init(component=component, resolution=resolution,
                        indir=basedir)
            init.set_shared_config(config, link=config_filename)

            default = Default(component=component, resolution=resolution,
                              indir=basedir, init=init, config=config,
                              include_tides=True)
            default.set_shared_config(config, link=config_filename)
            component.add_task(default)
