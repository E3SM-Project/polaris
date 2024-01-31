from polaris.config import PolarisConfigParser
from polaris.ocean.resolution import resolution_to_subdir
# from polaris.ocean.tasks.drying_slope.convergence import Convergence
# from polaris.ocean.tasks.drying_slope.decomp import Decomp
# from polaris.ocean.tasks.drying_slope.default import Default
from polaris.ocean.tasks.drying_slope.init import Init
from polaris.ocean.tasks.drying_slope.linear_drying import LinearDrying

# from polaris.ocean.tasks.drying_slope.loglaw import LogLaw


def add_drying_slope_tasks(component):
    """
    Add tasks for different drying slope tests to the ocean component

    component : polaris.ocean.Ocean
        the ocean component that the tasks will be added to
    """
    # forcing_type = 'tidal_cycle'

    # coord_type = 'sigma'
    # resdir = f'planar/drying_slope/{forcing_type}/{coord_type}/'
    # config_filename = 'drying_slope.cfg'

    # TODO
    # config = PolarisConfigParser(filepath=f'{resdir}/{config_filename}')

    # config.add_from_package('polaris.ocean.tasks.drying_slope',
    #                         'drying_slope.cfg')
    # convergence = Convergence(component=component, resolution=resolution,
    #                           indir=resdir, init=init,
    #                           coord_type=coord_type)
    # convergence.set_shared_config(config, link=config_filename)
    # component.add_task(convergence)

    # for coord_type in ['sigma', 'single_layer']:
    #     for resolution in [0.25, 1.]:
    #         resdir = resolution_to_subdir(resolution)
    #         resdir = f'planar/drying_slope/{forcing_type}/{coord_type}/' \
    #                  f'{resdir}'

    #         config_filename = 'drying_slope.cfg'

    # TODO check
    #         config = PolarisConfigParser(
    #             filepath=f'{resdir}/{config_filename}')

    #         config.add_from_package('polaris.ocean.tasks.drying_slope',
    #                                 'drying_slope.cfg')

    #         init = Init(component=component, resolution=resolution,
    #                     indir=resdir, baroclinic=False,
    #                     coord_type=coord_type)
    #         init.set_shared_config(config, link=config_filename)

    #         default = Default(component=component, resolution=resolution,
    #                           indir=resdir, init=init,
    #                           coord_type=coord_type)
    #         default.set_shared_config(config, link=config_filename)
    #         component.add_task(default)

    #         loglaw = LogLaw(component=component, resolution=resolution,
    #                         indir=resdir, init=init,
    #                         coord_type=coord_type)
    #         loglaw.set_shared_config(config, link=config_filename)
    #         component.add_task(loglaw)

    #         if resolution == 1.:
    #             decomp = Decomp(component=component, resolution=resolution,
    #                             indir=resdir, init=init,
    #                             coord_type=coord_type)
    #             decomp.set_shared_config(config, link=config_filename)
    #             component.add_task(decomp)

    resolution = 1.
    coord_type = 'sigma'
    resdir = resolution_to_subdir(resolution)
    resdir = f'planar/drying_slope/baroclinic/{coord_type}/' \
             f'{resdir}'

    config_filename = 'drying_slope.cfg'

    # TODO check
    config = PolarisConfigParser(filepath=f'{resdir}/{config_filename}')

    config.add_from_package('polaris.ocean.tasks.drying_slope',
                            'drying_slope.cfg')

    # forcing_type is not specified because only 'linear_drying' is available
    # for this test case
    linear_drying = LinearDrying(component=component,
                                 resolution=resolution, indir=resdir,
                                 coord_type=coord_type,
                                 time_integrator='split_explicit')
    linear_drying.set_shared_config(config, link=config_filename)
    component.add_task(linear_drying)
