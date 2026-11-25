"""
Whether a ``realistic_global`` ocean extends under Antarctic land ice.

The ocean domain comes from the ``[spherical_mesh]
antarctic_boundary_convention`` config option, which the e3sm/init cull step
uses to decide which cells belong to the ocean.  Under ``calving_front``, the
default, the ocean ends at the Antarctic calving front.  Under
``grounding_line`` it extends under floating ice, and under ``bedrock_zero``
under all ice whose bed is below sea level, with a thin film under grounded
ice.  The last two are what this package calls ice-shelf cavities.
"""

from polaris.mesh.spherical.coastline import (
    CONVENTION_OPTION,
    CONVENTION_SECTION,
    CONVENTIONS,
)

#: The convention that gives an ocean ending at the calving front
DEFAULT_CONVENTION = 'calving_front'


def get_antarctic_boundary_convention(config):
    """
    Get the Antarctic boundary convention from a config.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        The config, which normally holds the convention copied from the cull
        step's config or set in a user's config.  A config without it gets
        the default, ``calving_front``.

    Returns
    -------
    str
        The convention, one of ``calving_front``, ``grounding_line`` or
        ``bedrock_zero``
    """
    convention = config.get(
        CONVENTION_SECTION, CONVENTION_OPTION, fallback=DEFAULT_CONVENTION
    )
    if convention not in CONVENTIONS:
        valid = ', '.join(CONVENTIONS)
        raise ValueError(
            f'Unexpected {CONVENTION_OPTION} {convention!r}. Valid options '
            f'are: {valid}'
        )
    return convention


def has_ice_shelf_cavities(config):
    """
    Whether the ocean extends under Antarctic land ice.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        The config holding the Antarctic boundary convention

    Returns
    -------
    bool
        Whether the convention is anything other than ``calving_front``
    """
    return get_antarctic_boundary_convention(config) != DEFAULT_CONVENTION


def copy_antarctic_boundary_convention(config, source_config):
    """
    Copy the Antarctic boundary convention from another config, normally the
    shared config of the cull step, so that both start from the same default.
    A user's config still overrides it in both.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        The config to copy the convention to, modified in place

    source_config : polaris.config.PolarisConfigParser
        The config to copy the convention from
    """
    convention = get_antarctic_boundary_convention(source_config)
    config.set(
        CONVENTION_SECTION,
        CONVENTION_OPTION,
        convention,
        comment='Antarctic land-ice ownership convention, from the cull step',
    )


def check_cavities_supported(config):
    """
    Raise an error if ice-shelf cavities are requested with an ocean model
    that does not support them.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        The config holding the Antarctic boundary convention and the ocean
        model

    Raises
    ------
    ValueError
        If cavities are on and the ocean model is not MPAS-Ocean
    """
    if not has_ice_shelf_cavities(config):
        return
    model = config.get('ocean', 'model')
    if model != 'mpas-ocean':
        convention = get_antarctic_boundary_convention(config)
        raise ValueError(
            f'Ice-shelf cavities ({CONVENTION_OPTION} = {convention}) are '
            f'only supported with MPAS-Ocean, not {model}.'
        )
