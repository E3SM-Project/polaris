from polaris.config import PolarisConfigParser
from polaris.ocean.resolution import resolution_to_subdir
from polaris.ocean.tasks.drying_slope.baroclinic import Baroclinic
from polaris.ocean.tasks.drying_slope.barotropic import Barotropic
# from polaris.ocean.tasks.drying_slope.convergence import Convergence
from polaris.ocean.tasks.drying_slope.decomp import Decomp
from polaris.ocean.tasks.drying_slope.init import Init


def add_drying_slope_tasks(component):
    """
    Add tasks for different drying slope tests to the ocean component

    component : polaris.ocean.Ocean
        the ocean component that the tasks will be added to
    """
    config_filename = 'drying_slope.cfg'

    for coord_type in ['sigma', 'single_layer']:
        taskdir = f'planar/drying_slope/{coord_type}'
        config = PolarisConfigParser(filepath=f'{taskdir}/{config_filename}')

        config.add_from_package('polaris.ocean.tasks.drying_slope',
                                config_filename)

        # Add convergence test only for sigma coordinate
        # if coord_type = 'sigma':
        #     convergence = Convergence(component=component,
        #                               resolution=resolution,
        #                               indir=indir, init=init,
        #                               coord_type=coord_type)
        #     convergence.set_shared_config(config, link=config_filename)
        #     component.add_task(convergence)

        for resolution in [0.25, 1.]:
            resdir = resolution_to_subdir(resolution)

            indir = f'{taskdir}/{resdir}/barotropic'
            config = PolarisConfigParser(
                filepath=f'{indir}/{config_filename}')
            config.set('vertical_grid', 'coord_type', coord_type)

            config.add_from_package('polaris.ocean.tasks.drying_slope',
                                    config_filename)

            init = Init(component=component, resolution=resolution,
                        indir=indir, baroclinic=False)
            init.set_shared_config(config, link=config_filename)

            for method in ['standard', 'ramp']:
                indir = f'{taskdir}/{resdir}/barotropic'
                if coord_type == 'single_layer':
                    default = Barotropic(component=component,
                                         resolution=resolution,
                                         subdir=f'{indir}/{method}',
                                         init=init, method=method,
                                         coord_type=coord_type,
                                         drag_type='constant')
                else:
                    default = Barotropic(component=component,
                                         resolution=resolution,
                                         subdir=f'{indir}/{method}',
                                         init=init, method=method,
                                         coord_type=coord_type)
                default.set_shared_config(config, link=config_filename)
                component.add_task(default)

                if method == 'ramp':
                    loglaw = Barotropic(component=component,
                                        resolution=resolution,
                                        subdir=f'{indir}/{method}',
                                        init=init, method=method,
                                        drag_type='loglaw',
                                        coord_type=coord_type)
                    loglaw.set_shared_config(config, link=config_filename)
                    component.add_task(loglaw)

                if (method == 'ramp' and resolution == 1. and
                        coord_type == 'sigma'):
                    decomp = Decomp(component=component, resolution=resolution,
                                    indir=indir, init=init, method=method,
                                    coord_type=coord_type)
                    decomp.set_shared_config(config, link=config_filename)
                    component.add_task(decomp)

    for coord_type in ['sigma', 'z-star']:
        forcing_type = 'linear_drying'
        method = 'ramp'
        taskdir = f'planar/drying_slope/{coord_type}'
        resolution = 1.
        resdir = resolution_to_subdir(resolution)
        indir = f'{taskdir}/{resdir}/baroclinic'

        config = PolarisConfigParser(
            filepath=f'{indir}/{config_filename}')
        config.add_from_package('polaris.ocean.tasks.drying_slope',
                                config_filename)
        config.set('vertical_grid', 'coord_type', coord_type)

        init = Init(component=component, indir=indir,
                    resolution=resolution, baroclinic=True)
        init.set_shared_config(config, link=config_filename)

        baroclinic = Baroclinic(component=component, resolution=resolution,
                                init=init, subdir=f'{indir}/{method}',
                                coord_type=coord_type, method=method,
                                forcing_type=forcing_type,
                                time_integrator='split_explicit')
        baroclinic.set_shared_config(config, link=config_filename)
        component.add_task(baroclinic)
