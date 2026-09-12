import os

from polaris.config import PolarisConfigParser as PolarisConfigParser
from polaris.resolution import resolution_to_string
from polaris.tasks.ocean.baroclinic_channel.decomp import Decomp as Decomp
from polaris.tasks.ocean.baroclinic_channel.default import Default as Default
from polaris.tasks.ocean.baroclinic_channel.init import Init as Init
from polaris.tasks.ocean.baroclinic_channel.restart import Restart as Restart
from polaris.tasks.ocean.baroclinic_channel.rpe import Rpe as Rpe
from polaris.tasks.ocean.baroclinic_channel.threads import Threads as Threads


def add_baroclinic_channel_tasks(component):
    """
    Add tasks for different baroclinic channel tests to the ocean component

    component : polaris.tasks.ocean.Ocean
        the ocean component that the tasks will be added to
    """
    for resolution in [10.0, 4.0, 1.0]:
        resdir = resolution_to_string(resolution)
        resdir = f'planar/baroclinic_channel/{resdir}'

        config_filename = 'baroclinic_channel.cfg'
        config = PolarisConfigParser(
            filepath=os.path.join(component.name, resdir, config_filename)
        )
        config.add_from_package('polaris.ocean.eos', 'linear.cfg')
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

    for time_integrator in ['split_explicit', 'rk4']:
        _add_time_integrator_tasks(component, time_integrator)


def _add_time_integrator_tasks(component, time_integrator):
    """
    Add the 10-km decomp, restart and threads tasks for one time integrator,
    ``'split_explicit'`` or ``'rk4'``, in a directory named for it, so that a
    suite can run the two time steppers side by side.  RK4's stages and halo
    exchanges differ from those of the split-explicit stepper.
    """
    resolution = 10.0
    resdir = resolution_to_string(resolution)
    resdir = f'planar/baroclinic_channel/{time_integrator}/{resdir}'

    config_filename = 'baroclinic_channel.cfg'
    config = PolarisConfigParser(
        filepath=os.path.join(component.name, resdir, config_filename)
    )
    config.add_from_package('polaris.ocean.eos', 'linear.cfg')
    config.add_from_package(
        'polaris.tasks.ocean.baroclinic_channel', 'baroclinic_channel.cfg'
    )
    if time_integrator == 'rk4':
        config.add_from_package(
            'polaris.tasks.ocean.baroclinic_channel',
            'baroclinic_channel_rk4.cfg',
        )

    init = Init(component=component, resolution=resolution, indir=resdir)
    init.set_shared_config(config, link=config_filename)

    tasks = [
        Decomp(
            component=component, resolution=resolution, indir=resdir, init=init
        ),
        Restart(
            component=component, resolution=resolution, indir=resdir, init=init
        ),
        Threads(
            component=component, resolution=resolution, indir=resdir, init=init
        ),
    ]
    for task in tasks:
        task.set_shared_config(config, link=config_filename)
        component.add_task(task)
