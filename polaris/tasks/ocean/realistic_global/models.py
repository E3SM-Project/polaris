"""
Where the realistic-global steps for each ocean model live.

A step is *model-dependent* if its outputs, or the outputs of a step it depends
on, are written for one ocean model.  Each model's model-dependent steps live
in a directory named for the model, and have a copy of their family's config
file there, so one work directory can hold both models' steps without a setup
for one model overwriting the other's.  Every other step is *model-neutral* and
keeps the one directory both models share.
"""

#: The ocean models with a directory of their own
OCEAN_MODELS = ('mpas-ocean', 'omega')

#: The model whose steps a task is built with, before setup says which model
#: it is for
DEFAULT_MODEL = 'mpas-ocean'


def model_subdir(subdir: str, model: str) -> str:
    """
    The directory for a model's model-dependent steps within a family's
    directory.

    Parameters
    ----------
    subdir : str
        The family's directory, relative to the component.

    model : str
        The ocean model, one of :py:data:`OCEAN_MODELS`.

    Returns
    -------
    str
        The model's directory, relative to the component.

    Raises
    ------
    ValueError
        If ``model`` is not one of :py:data:`OCEAN_MODELS`.
    """
    if model not in OCEAN_MODELS:
        raise ValueError(
            f'Unknown ocean model {model!r}.  Expected one of '
            f'{", ".join(OCEAN_MODELS)}.'
        )
    return f'{subdir}/{model}'
