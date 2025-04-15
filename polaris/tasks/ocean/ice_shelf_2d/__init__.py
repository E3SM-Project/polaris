import os

from polaris.config import PolarisConfigParser as PolarisConfigParser
from polaris.resolution import resolution_to_string
from polaris.tasks.ocean.ice_shelf_2d.default import Default as Default
from polaris.tasks.ocean.ice_shelf_2d.init import Init as Init


def add_ice_shelf_2d_tasks(component):
    """
    Add tasks for different ice shelf 2-d tests to the ocean component

    component : polaris.ocean.Ocean
        the ocean component that the tasks will be added to
    """
    for resolution in [5.0, 2.0]:
        resdir = resolution_to_string(resolution)
        for coord_type in ['z-star', 'z-level']:
            basedir = f'planar/ice_shelf_2d/{resdir}/{coord_type}'

            config_filename = 'ice_shelf_2d.cfg'
            filepath = os.path.join(component.name, basedir, config_filename)
            config = PolarisConfigParser(filepath=filepath)
            config.add_from_package(
                'polaris.ocean.ice_shelf', 'ssh_adjustment.cfg'
            )
            config.add_from_package(
                'polaris.tasks.ocean.ice_shelf_2d', config_filename
            )
            config.set('vertical_grid', 'coord_type', coord_type)

            init = Init(
                component=component, resolution=resolution, indir=basedir
            )
            init.set_shared_config(config, link=config_filename)

            default = Default(
                component=component,
                resolution=resolution,
                indir=basedir,
                init=init,
                config=config,
            )
            default.set_shared_config(config, link=config_filename)
            component.add_task(default)

            default = Default(
                component=component,
                resolution=resolution,
                indir=basedir,
                init=init,
                config=config,
                include_viz=True,
            )
            default.set_shared_config(config, link=config_filename)
            component.add_task(default)

            default = Default(
                component=component,
                resolution=resolution,
                indir=basedir,
                init=init,
                config=config,
                include_restart=True,
            )
            default.set_shared_config(config, link=config_filename)
            component.add_task(default)

            default = Default(
                component=component,
                resolution=resolution,
                indir=basedir,
                init=init,
                config=config,
                include_tides=True,
            )
            default.set_shared_config(config, link=config_filename)
            component.add_task(default)

        # The only test case that makes sense with the single_layer coordinate
        # type is the one with barotropic tidal_forcing
        for coord_type in ['single_layer']:
            basedir = f'planar/ice_shelf_2d/{resdir}/{coord_type}'

            config_filename = 'ice_shelf_2d.cfg'
            filepath = os.path.join(component.name, basedir, config_filename)
            config = PolarisConfigParser(filepath=filepath)
            config.add_from_package(
                'polaris.ocean.ice_shelf', 'ssh_adjustment.cfg'
            )
            config.add_from_package(
                'polaris.tasks.ocean.ice_shelf_2d', config_filename
            )
            config.set('vertical_grid', 'coord_type', 'z-level')
            config.set('vertical_grid', 'vert_levels', '1')
            config.set('vertical_grid', 'partial_cell_type', 'None')

            init = Init(
                component=component, resolution=resolution, indir=basedir
            )
            init.set_shared_config(config, link=config_filename)

            default = Default(
                component=component,
                resolution=resolution,
                indir=basedir,
                init=init,
                config=config,
                include_tides=True,
            )
            default.set_shared_config(config, link=config_filename)
            component.add_task(default)
