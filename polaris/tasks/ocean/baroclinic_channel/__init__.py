from polaris.config import PolarisConfigParser as PolarisConfigParser
from polaris.ocean.resolution import (
    resolution_to_subdir as resolution_to_subdir,
)
from polaris.tasks.ocean.baroclinic_channel.decomp import Decomp as Decomp
from polaris.tasks.ocean.baroclinic_channel.default import Default as Default
from polaris.tasks.ocean.baroclinic_channel.init import Init as Init
from polaris.tasks.ocean.baroclinic_channel.restart import Restart as Restart
from polaris.tasks.ocean.baroclinic_channel.rpe import Rpe as Rpe
from polaris.tasks.ocean.baroclinic_channel.threads import Threads as Threads


def add_baroclinic_channel_tasks(component):
    """
    Add tasks for different baroclinic channel tests to the ocean component

    component : polaris.ocean.Ocean
        the ocean component that the tasks will be added to
    """
    for resolution in [10.0, 4.0, 1.0]:
        resdir = resolution_to_subdir(resolution)
        resdir = f'planar/baroclinic_channel/{resdir}'

        config_filename = 'baroclinic_channel.cfg'
        config = PolarisConfigParser(filepath=f'{resdir}/{config_filename}')
        config.add_from_package(
            'polaris.tasks.ocean.baroclinic_channel', 'baroclinic_channel.cfg'
        )

        init = Init(component=component, resolution=resolution, indir=resdir)
        init.set_shared_config(config, link=config_filename)

        default = Default(
            component=component, resolution=resolution, indir=resdir, init=init
        )
        default.set_shared_config(config, link=config_filename)
        component.add_task(default)

        if resolution == 10.0:
            decomp = Decomp(
                component=component,
                resolution=resolution,
                indir=resdir,
                init=init,
            )
            decomp.set_shared_config(config, link=config_filename)
            component.add_task(decomp)

            restart = Restart(
                component=component,
                resolution=resolution,
                indir=resdir,
                init=init,
            )
            restart.set_shared_config(config, link=config_filename)
            component.add_task(restart)

            threads = Threads(
                component=component,
                resolution=resolution,
                indir=resdir,
                init=init,
            )
            threads.set_shared_config(config, link=config_filename)
            component.add_task(threads)

        component.add_task(
            Rpe(
                component=component,
                resolution=resolution,
                indir=resdir,
                init=init,
                config=config,
            )
        )
