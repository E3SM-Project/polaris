WETTING_DRYING_PACKAGE = 'polaris.ocean.ice_shelf'


def add_wetting_drying_yaml_files(step, thin_film=False, split_explicit=False):
    """
    Add MPAS-Ocean's wetting and drying options for ocean runs under land
    ice to a model step.

    The options are shared by every ice-shelf task that runs with wetting
    and drying, so that SSH adjustment and the forward runs of all of them
    treat thin columns the same way.

    Parameters
    ----------
    step : polaris.ModelStep
        The step to add the options to, typically from its
        ``dynamic_model_config()`` method

    thin_film : bool, optional
        Whether there is a thin film under grounded ice, in which case
        velocities are also ramped down in thin columns

    split_explicit : bool, optional
        Whether the step uses the ``split_explicit`` time integrator, in
        which case the potential-vorticity form of the Coriolis term is
        split between the barotropic and baroclinic modes
    """
    step.add_yaml_file(WETTING_DRYING_PACKAGE, 'wetting_drying.yaml')
    if split_explicit:
        step.add_yaml_file(WETTING_DRYING_PACKAGE, 'split_explicit.yaml')
    if thin_film:
        step.add_yaml_file(
            WETTING_DRYING_PACKAGE, 'thin_film_wetting_drying.yaml'
        )
