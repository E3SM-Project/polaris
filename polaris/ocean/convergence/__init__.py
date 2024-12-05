def get_resolution_for_task(config, refinement_factor,
                            refinement='both'):
    """
    Get the resolution for a step in a convergence task

    Parameters
    ----------
    config : polaris.Config
        The config options for this task

    refinement_factor : float
        The factor by which either resolution or time is refined for this step

    refinement : str, optional
        Whether to refine in space, time or both

    Returns
    -------
    resolution : float
        The resolution corresponding to the refinement_factor and convergence
        test type
    """
    if refinement == 'both':
        option = 'refinement_factors_space'
    else:
        option = f'refinement_factors_{refinement}'
    base_resolution = config.getfloat('convergence', 'base_resolution')
    refinement_factors = config.getlist('convergence', option, dtype=float)

    if refinement_factor not in refinement_factors:
        raise ValueError(
            f'refinement_factor {refinement_factor} not found in config '
            f'option {option}:\n {refinement_factors}')

    if refinement == 'time':
        resolution = base_resolution
    else:
        resolution = refinement_factor * base_resolution

    return resolution


def get_timestep_for_task(config, refinement_factor,
                          refinement='both'):
    """
    Get the time step for a forward step in a convergence task

    Parameters
    ----------
    config : polaris.Config
        The config options for this task

    refinement_factor : float
        The factor by which either resolution or time is refined for this step

    refinement : str, optional
        Whether to refine in space, time or both

    Returns
    -------
    resolution : float
        The resolution corresponding to the refinement_factor and convergence
        test type
    """

    if refinement == 'both':
        option = 'refinement_factors_space'
    else:
        option = f'refinement_factors_{refinement}'
    base_resolution = config.getfloat('convergence', 'base_resolution')
    refinement_factors = config.getlist('convergence', option, dtype=float)

    if refinement_factor not in refinement_factors:
        raise ValueError(
            f'refinement_factor {refinement_factor} not found in config '
            f'option {option}:\n {refinement_factors}')

    resolution = get_resolution_for_task(
        config, refinement_factor, refinement=refinement)

    section = config['convergence_forward']
    time_integrator = section.get('time_integrator')
    # dt is proportional to resolution: default 30 seconds per km
    if time_integrator == 'RK4':
        dt_per_km = section.getfloat('rk4_dt_per_km')
        btr_timestep = 0.
    else:
        dt_per_km = section.getfloat('split_dt_per_km')
        btr_dt_per_km = section.getfloat('btr_dt_per_km')
        for idx, refinement_factor in enumerate(refinement_factors):
            if refinement == 'time':
                btr_timestep = btr_dt_per_km * base_resolution * \
                    refinement_factor
            elif refinement == 'space':
                btr_timestep = btr_dt_per_km * base_resolution
            else:
                btr_timestep = btr_dt_per_km * resolution
    if refinement == 'time':
        timestep = dt_per_km * refinement_factor * resolution
    elif refinement == 'space':
        timestep = dt_per_km * base_resolution
    else:
        timestep = dt_per_km * resolution

    return timestep, btr_timestep
