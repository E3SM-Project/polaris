import os

from polaris.config import PolarisConfigParser
from polaris.step import Step

from .product import ShortwaveExtinctionProductStep

SHORTWAVE_EXTINCTION_SUBDIR = (
    'spherical/realistic_global/forcing/shortwave_extinction'
)


def get_shortwave_extinction_steps(component):
    """
    Get the shared steps for building the reusable shortwave extinction
    coefficient product.

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        The ocean component the steps belong to.

    Returns
    -------
    steps : dict of {str: polaris.Step}
        All shared steps keyed by their suggested symlink names for use in a
        task.

    config : polaris.config.PolarisConfigParser
        The shared config options for the steps.
    """
    config_filename = 'shortwave_extinction.cfg'

    def create():
        config = PolarisConfigParser(filepath=filepath)
        config.add_from_package(
            'polaris.tasks.ocean.realistic_global.forcing.'
            'shortwave_extinction',
            config_filename,
        )
        return config

    filepath = os.path.join(
        component.name, SHORTWAVE_EXTINCTION_SUBDIR, config_filename
    )
    config = component.get_or_create_shared_config(
        filepath=filepath, create=create
    )

    product_step = component.get_or_create_shared_step(
        step_cls=ShortwaveExtinctionProductStep,
        subdir=os.path.join(SHORTWAVE_EXTINCTION_SUBDIR, 'extinction_product'),
        config=config,
        config_filename=config_filename,
    )

    steps: dict[str, Step] = {'extinction_product': product_step}
    return steps, config
