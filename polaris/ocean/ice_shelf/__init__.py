from typing import Dict

from polaris import Task
from polaris.ocean.ice_shelf.freeze import compute_freezing_temperature
from polaris.ocean.ice_shelf.pressure import (
    compute_land_ice_draft_from_pressure,
    compute_land_ice_pressure_from_draft,
    compute_land_ice_pressure_from_thickness,
)
from polaris.ocean.ice_shelf.ssh_adjustment import SshAdjustment
from polaris.ocean.ice_shelf.ssh_forward import SshForward


class IceShelfTask(Task):

    """
    A class for tasks with domains containing ice shelves

    Attributes
    ----------
    sshdir : string
        The directory to put the ssh_adjustment steps in

    component : polaris.ocean.Ocean
        The ocean component that this task belongs to

    min_resolution : float
        The resolution of the test case in km
    """
    def __init__(self, component, min_resolution, name, subdir, sshdir=None):
        """
        Construct ice shelf task

        Parameters
        ----------
        component : polaris.ocean.Ocean
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

    def setup_ssh_adjustment_steps(self, mesh_filename, graph_filename,
                                   init_filename, config, config_filename,
                                   ForwardStep, package=None,
                                   yaml_filename='ssh_forward.yaml',
                                   yaml_replacements=None):

        """
        Setup ssh_forward and ssh_adjustment steps for all iterations

        Parameters
        ----------
        config : polaris.config.PolarisConfigParser
            The configuration for this task

        mesh_filename : str
            the mesh filename (relative to the base work directory)

        graph_filename : str
            the graph filename (relative to the base work directory)

        init_filename : str
            the initial condition filename (relative to the base work
            directory)

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
        shared_step : polaris.Step
            the final ssh_adjustment step that produces the input to the next
            forward step
        """
        min_resolution = self.min_resolution
        component = self.component
        indir = self.sshdir

        num_iterations = config.getint('ssh_adjustment', 'iterations')

        # for the first iteration, ssh_forward step is run from the initial
        # state
        current_init_filename = init_filename
        for iteration in range(num_iterations):
            name = f'ssh_forward_{iteration}'
            subdir = f'{indir}/ssh_adjustment/{name}'
            if subdir in component.steps:
                shared_step = component.steps[subdir]
            else:
                ssh_forward = ForwardStep(
                    component=component, min_resolution=min_resolution,
                    indir=indir, graph_filename=graph_filename,
                    init_filename=current_init_filename, name=name,
                    package=package, yaml_filename=yaml_filename,
                    yaml_replacements=yaml_replacements)
                ssh_forward.set_shared_config(config, link=config_filename)
                shared_step = ssh_forward
            if indir == self.subdir:
                symlink = None
            else:
                symlink = f'ssh_adjustment/{name}'
            self.add_step(shared_step, symlink=symlink)

            name = f'ssh_adjust_{iteration}'
            subdir = f'{indir}/ssh_adjustment/{name}'
            if subdir in component.steps:
                shared_step = component.steps[subdir]
            else:
                ssh_adjust = SshAdjustment(
                    component=component, indir=indir, name=name,
                    mesh_filename=mesh_filename, forward=ssh_forward)
                ssh_adjust.set_shared_config(config, link=config_filename)
                shared_step = ssh_adjust
            if indir == self.subdir:
                symlink = None
            else:
                symlink = f'ssh_adjustment/{name}'
            self.add_step(shared_step, symlink=symlink)
            # for the next iteration, ssh_forward is run from the adjusted
            # initial state (the output of ssh_adustment)
            current_init_filename = f'{shared_step.path}/output.nc'

        return shared_step
