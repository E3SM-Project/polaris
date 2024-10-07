import numpy as np


def get_resolution_for_task(config, refinement_factor,
                            refinement='both'):

    base_resolution = config.getfloat('convergence', 'base_resolution')
    refinement_factors = config.getlist('convergence',
                                        'refinement_factors',
                                        dtype=float)

    if refinement_factor not in refinement_factors:
        raise ValueError(
            'refinement_factor not found in config option refinement_factors')

    if refinement == 'time':
        resolution = base_resolution
    else:
        resolution = refinement_factor * base_resolution

    return resolution


def get_timestep_for_task(config, refinement_factor,
                          refinement='both'):

    base_resolution = config.getfloat('convergence', 'base_resolution')
    refinement_factors = config.getlist('convergence',
                                        'refinement_factors',
                                        dtype=float)

    if refinement_factor not in refinement_factors:
        raise ValueError(
            'refinement_factor not found in config option refinement_factors')

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
        timestep = dt_per_km * refinement_factor * base_resolution
    elif refinement == 'space':
        timestep = dt_per_km * base_resolution
    else:
        timestep = dt_per_km * resolution

    return timestep, btr_timestep
