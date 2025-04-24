def compute_density(config, temperature, salinity):
    eos_type = config.get('ocean', 'eos_type')
    if eos_type == 'linear':
        density = _compute_linear_density(config, temperature, salinity)
    return density


def _compute_linear_density(config, temperature, salinity):
    alpha = config.getfloat('ocean', 'eos_linear_alpha')
    beta = config.getfloat('ocean', 'eos_linear_beta')
    rhoref = config.getfloat('ocean', 'eos_linear_rhoref')
    Tref = config.getfloat('ocean', 'eos_linear_Tref')
    Sref = config.getfloat('ocean', 'eos_linear_Sref')
    density = rhoref + -alpha * (temperature - Tref) + beta * (salinity - Sref)
    return density
