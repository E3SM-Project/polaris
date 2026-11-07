"""
Which models the staged component inputs can be built for.

The gate is built now, while only MPAS is supported, so that adding Omega
fills a named gap rather than retrofitting model selection into steps that
quietly assumed MPAS.
"""

from polaris.config import PolarisConfigParser

#: The ocean models ``[component_inputs] ocean_model`` accepts.
OCEAN_MODELS = ('mpas-ocean', 'omega')

#: The sea-ice models ``[component_inputs] seaice_model`` accepts.
SEAICE_MODELS = ('mpas-seaice', 'none')


def check_ocean_model(config: PolarisConfigParser) -> str:
    """
    The configured ocean model, if its files can be staged.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        The config options for the component-input steps.

    Returns
    -------
    str
        The ocean model.

    Raises
    ------
    ValueError
        If the model is not one this workflow knows about.

    NotImplementedError
        If it is Omega, whose packaging is not supported yet.
    """
    model = config.get('component_inputs', 'ocean_model').strip()
    if model not in OCEAN_MODELS:
        raise ValueError(
            f'Unknown [component_inputs] ocean_model {model!r}.  Expected one '
            f'of {", ".join(OCEAN_MODELS)}.'
        )
    if model == 'omega':
        raise NotImplementedError(
            'Staging component inputs for Omega is not supported yet.  Set '
            '[component_inputs] ocean_model = mpas-ocean.'
        )
    return model


def check_seaice_model(config: PolarisConfigParser) -> str:
    """
    The configured sea-ice model, if its files can be staged.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        The config options for the component-input steps.

    Returns
    -------
    str
        The sea-ice model, or ``'none'`` if no sea-ice files are wanted.

    Raises
    ------
    ValueError
        If the model is not one this workflow knows about.
    """
    model = config.get('component_inputs', 'seaice_model').strip()
    if model not in SEAICE_MODELS:
        raise ValueError(
            f'Unknown [component_inputs] seaice_model {model!r}.  Expected '
            f'one of {", ".join(SEAICE_MODELS)}.'
        )
    return model
