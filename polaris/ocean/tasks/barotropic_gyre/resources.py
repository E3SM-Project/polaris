def compute_max_time_step(config):
    u_max = 1  # m/s
    stability_parameter_max = 0.5
    resolution = config.getfloat('barotropic_gyre', 'resolution')
    f_0 = config.getfloat("barotropic_gyre", "f_0")
    dt_max = min(stability_parameter_max * resolution * 1e3 /
                 (2 * u_max),
                 stability_parameter_max / f_0)
    return dt_max
