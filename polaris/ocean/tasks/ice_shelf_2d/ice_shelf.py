from typing import Dict

from polaris import Step, Task
from polaris.ocean.tasks.ice_shelf_2d.ssh_adjustment import SshAdjustment
from polaris.ocean.tasks.ice_shelf_2d.ssh_forward import SshForward


class IceShelfTask(Task):

    """
    shared_steps : dict of dict of polaris.Steps
        The shared steps to include as symlinks
    """
    def __init__(self, component, resolution, indir, name):
        super().__init__(component=component, name=name, indir=indir)
        self.indir = indir
        self.component = component
        self.resolution = resolution

    def _setup_ssh_adjustment_steps(self, init, config, config_filename):

        resolution = self.resolution
        component = self.component
        indir = self.indir

        # TODO config
        num_iterations = 10
        shared_steps: Dict[str, Step] = dict()

        iteration = 0
        name = f'ssh_forward_{iteration}'
        ssh_forward = SshForward(
            component=component, resolution=resolution, indir=indir,
            mesh=init, init=init, name=name)
        ssh_forward.set_shared_config(config, link=config_filename)
        shared_steps[name] = ssh_forward

        for iteration in range(1, num_iterations):
            name = f'ssh_adjust_{iteration - 1}'
            ssh_adjust = SshAdjustment(
                component=component, resolution=resolution, indir=indir,
                name=name, init=init, forward=ssh_forward)
            ssh_adjust.set_shared_config(config, link=config_filename)
            shared_steps[name] = ssh_adjust
            name = f'ssh_forward_{iteration}'
            ssh_forward = SshForward(
                component=component, resolution=resolution, indir=indir,
                mesh=init, init=ssh_adjust, name=name)
            ssh_forward.set_shared_config(config, link=config_filename)
            shared_steps[name] = ssh_forward

        iteration = num_iterations
        name = f'ssh_adjust_{iteration - 1}'
        ssh_adjust = SshAdjustment(
            component=component, resolution=resolution, indir=indir,
            name=name, init=init, forward=ssh_forward)
        ssh_adjust.set_shared_config(config, link=config_filename)
        shared_steps[name] = ssh_adjust
        self.init_step = ssh_adjust

        for name, shared_step in shared_steps.items():
            self.add_step(shared_step, symlink=name)
        return ssh_adjust
