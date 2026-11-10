"""
Which ocean model the staged component inputs can be built for.

The ocean initial condition is the restart of a dynamic adjustment, which runs
whichever model the ocean component was set up with (``--ocean_model``, or
detected from the build).  The staged files can only be for that same model,
so the model is taken from the ocean component rather than from an option of
this workflow's own, which could disagree with it.

The gate is built now, while only MPAS-Ocean is supported, so that adding
Omega fills a named gap rather than retrofitting model selection into steps
that quietly assumed MPAS-Ocean.
"""

from polaris.tasks.ocean import ocean


def check_ocean_model() -> str:
    """
    The ocean model the dynamic adjustment runs, if its files can be staged.

    Only meaningful during setup, after the ocean component has been
    configured.

    Returns
    -------
    str
        The ocean model.

    Raises
    ------
    NotImplementedError
        If it is Omega, whose packaging is not supported yet.

    ValueError
        If the ocean component has no model or one this workflow does not
        know about.
    """
    model = ocean.model
    if model == 'omega':
        raise NotImplementedError(
            'Staging component inputs for Omega is not supported yet.  Set '
            'up with --ocean_model mpas-ocean, or point --ocean_path at an '
            'MPAS-Ocean build.'
        )
    if model != 'mpas-ocean':
        raise ValueError(
            f'Cannot stage component inputs for ocean model {model!r}.  '
            f'Only mpas-ocean is supported.'
        )
    return model
