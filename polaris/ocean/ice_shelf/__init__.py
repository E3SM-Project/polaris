from typing import Dict

from polaris import Step, Task
from polaris.ocean.ice_shelf.ssh_adjustment import SshAdjustment
from polaris.ocean.ice_shelf.ssh_forward import SshForward


class IceShelfTask(Task):

    """
    shared_steps : dict of dict of polaris.Steps
        The shared steps to include as symlinks
    """
    def __init__(self, component, resolution, name, subdir, sshdir=None):
        if sshdir is None:
            sshdir = subdir
        super().__init__(component=component, name=name, subdir=subdir)
        self.sshdir = sshdir
        self.component = component
        self.resolution = resolution

    def setup_ssh_adjustment_steps(self, init, config, config_filename,
                                   package=None,
                                   yaml_filename='ssh_forward.yaml',
                                   yaml_replacements=None):

        resolution = self.resolution
        component = self.component
        indir = self.sshdir

        num_iterations = config.getint('ssh_adjustment', 'iterations')

        # for the first iteration, ssh_forward step is run from the initial
        # state
        current_init = init
        for iteration in range(num_iterations):
            name = f'ssh_forward_{iteration}'
            ssh_forward = SshForward(
                component=component, resolution=resolution, indir=indir,
                mesh=init, init=current_init, name=name, package=package,
                yaml_filename=yaml_filename,
                yaml_replacements=yaml_replacements)
            ssh_forward.set_shared_config(config, link=config_filename)
            subdir = f'{indir}/ssh_adjustment/{name}'
            if subdir in component.steps:
                shared_step = component.steps[subdir]
            else:
                shared_step = ssh_forward
            self.add_step(shared_step, symlink=f'ssh_adjustment/{name}')

            name = f'ssh_adjust_{iteration}'
            ssh_adjust = SshAdjustment(
                component=component, resolution=resolution, indir=indir,
                name=name, init=init, forward=ssh_forward)
            ssh_adjust.set_shared_config(config, link=config_filename)
            subdir = f'{indir}/ssh_adjustment/{name}'
            if subdir in component.steps:
                shared_step = component.steps[subdir]
            else:
                shared_step = ssh_adjust
            self.add_step(shared_step, symlink=f'ssh_adjustment/{name}')
            # for the next iteration, ssh_forward is run from the adjusted
            # initial state (the output of ssh_adustment)
            current_init = shared_step

        return shared_step
