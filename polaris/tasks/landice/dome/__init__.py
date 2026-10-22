import os

from polaris.config import PolarisConfigParser
from polaris.resolution import resolution_to_string
from polaris.tasks.landice.dome.decomp import Decomp as Decomp
from polaris.tasks.landice.dome.init import Init as Init
from polaris.tasks.landice.dome.restart import Restart as Restart
from polaris.tasks.landice.dome.smoke_test import SmokeTest as SmokeTest


def add_dome_tasks(component):
    """
    Add tasks for the dome test to the landice component

    component : polaris.tasks.landice.Landice
        the landice component that the tasks will be added to
    """
    resolution = 2.0
    resdir = f'dome/{resolution_to_string(resolution)}'

    config_filename = 'dome.cfg'
    config = PolarisConfigParser(
        filepath=os.path.join(component.name, resdir, config_filename)
    )
    config.add_from_package('polaris.tasks.landice.dome', config_filename)

    init = Init(component=component, resolution=resolution, indir=resdir)
    init.set_shared_config(config, link=config_filename)

    for velocity_solver in ['sia', 'FO']:
        indir = f'{resdir}/{velocity_solver.lower()}'
        for task_cls in [SmokeTest, Decomp, Restart]:
            task = task_cls(
                component=component,
                velocity_solver=velocity_solver,
                indir=indir,
                init=init,
            )
            task.set_shared_config(config, link=config_filename)
            component.add_task(task)
