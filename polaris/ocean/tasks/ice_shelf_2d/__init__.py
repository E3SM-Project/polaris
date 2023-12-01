from typing import Dict

from polaris import Step
from polaris.config import PolarisConfigParser
from polaris.ocean.resolution import resolution_to_subdir
from polaris.ocean.tasks.ice_shelf_2d.default import Default
from polaris.ocean.tasks.ice_shelf_2d.init import Init
from polaris.ocean.tasks.ice_shelf_2d.ssh_adjustment import SshAdjustment
from polaris.ocean.tasks.ice_shelf_2d.ssh_forward import SshForward


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
                                'ice_shelf_2d.cfg')

        shared_steps: Dict[str, Step] = dict()

        init = Init(component=component, resolution=resolution, indir=resdir)
        init.set_shared_config(config, link=config_filename)
        shared_steps['init'] = init

        num_iterations = 10

        iteration = 0
        name = f'ssh_forward_{iteration}'
        ssh_forward = SshForward(
            component=component, resolution=resolution, indir=resdir,
            mesh=init, init=shared_steps['init'], name=name)
        ssh_forward.set_shared_config(config, link=config_filename)
        shared_steps[name] = ssh_forward

        for iteration in range(1, num_iterations):
            name = f'ssh_adjust_{iteration - 1}'
            ssh_adjust = SshAdjustment(
                component=component, resolution=resolution, indir=resdir,
                name=name, init=shared_steps['init'], forward=ssh_forward)
            ssh_adjust.set_shared_config(config, link=config_filename)
            shared_steps[name] = ssh_adjust
            name = f'ssh_forward_{iteration}'
            ssh_forward = SshForward(
                component=component, resolution=resolution, indir=resdir,
                mesh=init, init=ssh_adjust, name=name)
            ssh_forward.set_shared_config(config, link=config_filename)
            shared_steps[name] = ssh_forward

        iteration = num_iterations
        name = f'ssh_adjust_{iteration - 1}'
        ssh_adjust = SshAdjustment(
            component=component, resolution=resolution, indir=resdir,
            name=name, init=shared_steps['init'], forward=ssh_forward)
        ssh_adjust.set_shared_config(config, link=config_filename)
        shared_steps[name] = ssh_adjust

        default = Default(component=component, resolution=resolution,
                          indir=resdir, mesh=init, init=ssh_adjust,
                          shared_steps=shared_steps)
        default.set_shared_config(config, link=config_filename)
        component.add_task(default)
