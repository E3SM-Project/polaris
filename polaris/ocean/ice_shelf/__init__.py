from typing import Dict

from polaris import Step, Task
from polaris.ocean.ice_shelf.ssh_adjustment import SshAdjustment
from polaris.ocean.ice_shelf.ssh_forward import SshForward


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

    def _setup_ssh_adjustment_steps(self, init, config, config_filename,
                                    package=None,
                                    yaml_filename='ssh_forward.yaml',
                                    yaml_replacements=None):

        resolution = self.resolution
        component = self.component
        indir = self.indir

        num_iterations = config.getint('ssh_adjustment', 'iterations')
        shared_steps: Dict[str, Step] = dict()

        iteration = 0
        name = f'ssh_forward_{iteration}'
        ssh_forward = SshForward(
            component=component, resolution=resolution, indir=indir,
            mesh=init, init=init, name=name, package=package,
            yaml_filename=yaml_filename, yaml_replacements=yaml_replacements)
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
                mesh=init, init=ssh_adjust, name=name, package=package,
                yaml_filename=yaml_filename,
                yaml_replacements=yaml_replacements)
            ssh_forward.set_shared_config(config, link=config_filename)
            shared_steps[name] = ssh_forward

        iteration = num_iterations
        name = f'ssh_adjust_{iteration - 1}'
        ssh_adjust = SshAdjustment(
            component=component, resolution=resolution, indir=indir,
            name=name, init=init, forward=ssh_forward)
        ssh_adjust.set_shared_config(config, link=config_filename)
        shared_steps[name] = ssh_adjust
        subdir = f'{indir}/ssh_adjustment/{name}'
        if subdir in component.steps:
            ssh_adjust = component.steps[subdir]

        for name, shared_step in shared_steps.items():
            subdir = f'{indir}/ssh_adjustment/{name}'
            if subdir in component.steps:
                shared_step = component.steps[subdir]
            self.add_step(shared_step, symlink=f'ssh_adjustment/{name}')
        return ssh_adjust
