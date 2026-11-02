from polaris.ocean.ice_shelf.ssh_adjustment import SshAdjustment


def get_ssh_adjustment_steps(
    component,
    sshdir,
    min_resolution,
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
    Get or create the shared ssh_forward and ssh_adjustment steps for all
    iterations

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        The ocean component the steps belong to

    sshdir : str
        The directory to put the ssh_adjustment steps in

    min_resolution : float
        The resolution of the mesh in km

    mesh_filename : str
        the mesh filename (relative to the base work directory)

    graph_target: str
        the graph filename (relative to the base work directory)

    init_filename : str
        the initial condition filename (relative to the base work
        directory)

    config : polaris.config.PolarisConfigParser
        The shared configuration for the steps

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
    steps : dict of str to polaris.Step
        The steps in the order they run, keyed by their paths relative to
        ``sshdir``, ``ssh_adjustment/<name>``

    final_step : polaris.Step
        the final ssh_adjustment step that produces the input to the next
        forward step
    """
    num_iterations = config.getint('ssh_adjustment', 'iterations')

    steps = dict()
    # for the first iteration, ssh_forward step is run from the initial
    # state
    current_init_filename = init_filename
    final_step = None
    for iteration in range(num_iterations):
        name = f'ssh_forward_{iteration}'
        ssh_forward = component.get_or_create_shared_step(
            step_cls=ForwardStep,
            subdir=f'{sshdir}/ssh_adjustment/{name}',
            config=config,
            config_filename=config_filename,
            min_resolution=min_resolution,
            init_filename=current_init_filename,
            graph_target=graph_target,
            mesh_filename=mesh_filename,
            name=name,
            package=package,
            yaml_filename=yaml_filename,
            yaml_replacements=yaml_replacements,
        )
        steps[f'ssh_adjustment/{name}'] = ssh_forward

        name = f'ssh_adjust_{iteration}'
        ssh_adjust = component.get_or_create_shared_step(
            step_cls=SshAdjustment,
            subdir=f'{sshdir}/ssh_adjustment/{name}',
            config=config,
            config_filename=config_filename,
            mesh_filename=mesh_filename,
            forward=ssh_forward,
            name=name,
        )
        steps[f'ssh_adjustment/{name}'] = ssh_adjust
        # for the next iteration, ssh_forward is run from the adjusted
        # initial state (the output of ssh_adustment)
        current_init_filename = f'{ssh_adjust.path}/output.nc'
        final_step = ssh_adjust

    return steps, final_step
