def compute_density(config, temperature, salinity):
    eos_type = config.get('ocean', 'eos_type')
    if eos_type == 'linear':
        density = _compute_linear_density(config, temperature, salinity)
    return density


def _compute_linear_density(config, temperature, salinity):
    section = config['ocean']
    alpha = section.getfloat('eos_linear_alpha')
    beta = section.getfloat('eos_linear_beta')
    rhoref = section.getfloat('eos_linear_rhoref')
    Tref = section.getfloat('eos_linear_Tref')
    Sref = section.getfloat('eos_linear_Sref')
    density = rhoref + -alpha * (temperature - Tref) + beta * (salinity - Sref)
    return density
