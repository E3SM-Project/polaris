from typing import Dict as Dict

from polaris import (
    Step as Step,
)
from polaris import (
    Task as Task,
)
from polaris.ocean.ice_shelf.ssh_adjustment import (
    SshAdjustment as SshAdjustment,
)
from polaris.ocean.ice_shelf.ssh_forward import SshForward as SshForward


class IceShelfTask(Task):
    """
    A class for tasks with domains containing ice shelves

    Attributes
    ----------
    sshdir : string
        The directory to put the ssh_adjustment steps in

    component : polaris.tasks.ocean.Ocean
        The ocean component that this task belongs to

    min_resolution : float
        The resolution of the test case in km
    """

    def __init__(self, component, min_resolution, name, subdir, sshdir=None):
        """
        Construct ice shelf task

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this task belongs to

        min_resolution : float
            The resolution of the test case in km

        name : string
            The name of the step

        subdir : string
            The subdirectory for the step

        sshdir : string, optional
            The directory to put the ssh_adjustment steps in. If None,
            defaults to subdir.
        """
        if sshdir is None:
            sshdir = subdir
        super().__init__(component=component, name=name, subdir=subdir)
        self.sshdir = sshdir
        self.component = component
        self.min_resolution = min_resolution

    def setup_ssh_adjustment_steps(
        self,
        mesh_filename,
        graph_target,
        init_filename,
        config,
        config_filename,
        ForwardStep,
        package=None,
        yaml_filename='ssh_forward.yaml',
        yaml_replacements=None,
    ):
        """
        Setup ssh_forward and ssh_adjustment steps for all iterations

        Parameters
        ----------
        mesh_filename : str
            the mesh filename (relative to the base work directory)

        graph_target: str
            the graph filename (relative to the base work directory)

        init_filename : str
            the initial condition filename (relative to the base work
            directory)

        config : polaris.config.PolarisConfigParser
            The configuration for this task

        config_filename : str
            the configuration filename

        ForwardStep : polaris.ocean.ice_shelf.ssh_forward.SshForward
            the step class used to create ssh_forward steps

        package : Package
            The package name or module object that contains ``namelist``
            from which ssh_forward steps will derive their configuration

        yaml_filename : str, optional
            the yaml filename used for ssh_forward steps

        yaml_replacements : Dict, optional
            key, string combinations for templated replacements in the yaml
            file

        Returns
        -------
        final_step : polaris.Step
            the final ssh_adjustment step that produces the input to the next
            forward step
        """
        min_resolution = self.min_resolution
        component = self.component
        sshdir = self.sshdir

        num_iterations = config.getint('ssh_adjustment', 'iterations')

        # for the first iteration, ssh_forward step is run from the initial
        # state
        current_init_filename = init_filename
        for iteration in range(num_iterations):
            name = f'ssh_forward_{iteration}'
            subdir = f'{sshdir}/ssh_adjustment/{name}'
            ssh_forward = component.get_or_create_shared_step(
                step_cls=ForwardStep,
                subdir=subdir,
                config=config,
                config_filename=config_filename,
                min_resolution=min_resolution,
                init_filename=current_init_filename,
                graph_target=graph_target,
                name=name,
                package=package,
                yaml_filename=yaml_filename,
                yaml_replacements=yaml_replacements,
            )
            if sshdir == self.subdir:
                symlink = None
            else:
                symlink = f'ssh_adjustment/{name}'
            self.add_step(ssh_forward, symlink=symlink)

            name = f'ssh_adjust_{iteration}'
            subdir = f'{sshdir}/ssh_adjustment/{name}'
            ssh_adjust = component.get_or_create_shared_step(
                step_cls=SshAdjustment,
                subdir=subdir,
                config=config,
                config_filename=config_filename,
                mesh_filename=mesh_filename,
                forward=ssh_forward,
                name=name,
            )
            if sshdir == self.subdir:
                symlink = None
            else:
                symlink = f'ssh_adjustment/{name}'
            self.add_step(ssh_adjust, symlink=symlink)
            # for the next iteration, ssh_forward is run from the adjusted
            # initial state (the output of ssh_adustment)
            current_init_filename = f'{ssh_adjust.path}/output.nc'
            final_step = ssh_adjust

        return final_step
