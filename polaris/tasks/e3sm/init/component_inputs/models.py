"""
Which ocean model a component-inputs task stages files for.

Each task that stages ocean products is built for one ocean model, the way an
E3SM configuration is.  The ocean initial condition is the restart of a
dynamic adjustment, which runs whichever model the ocean component was set up
with (``--ocean_model``, or detected from the build), so the two have to
agree, and setup stops when they do not rather than choosing one.
"""

from polaris.tasks.ocean import ocean
from polaris.tasks.ocean.realistic_global.models import OCEAN_MODELS


def check_ocean_model(model: str) -> None:
    """
    Check that the ocean component is set up for a task's ocean model.

    Only meaningful during setup, after the ocean component has been
    configured.

    Parameters
    ----------
    model : str
        The ocean model the task stages files for, one of
        :py:data:`~polaris.tasks.ocean.realistic_global.models.OCEAN_MODELS`.

    Raises
    ------
    ValueError
        If the ocean component is set up for another model.
    """
    if model not in OCEAN_MODELS:
        raise ValueError(
            f'Cannot stage component inputs for ocean model {model!r}.  '
            f'Expected one of {", ".join(OCEAN_MODELS)}.'
        )
    if ocean.model != model:
        raise ValueError(
            f'This task stages component inputs for {model}, but the ocean '
            f'component is set up for {ocean.model}.  Set up with '
            f'--ocean_model {model}, or point --ocean_path at a {model} '
            f'build.'
        )
