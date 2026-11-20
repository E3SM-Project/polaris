"""
Where the realistic-global steps for each ocean model live.

A step is *model-dependent* if its outputs, or the outputs of a step it depends
on, are written for one ocean model.  Each model's model-dependent steps live
in a directory named for the model, and have a copy of their family's config
file there, so one work directory can hold both models' steps without a setup
for one model overwriting the other's.  Every other step is *model-neutral* and
keeps the one directory both models share.

The model is not known when tasks are built, only once the ocean component has
been configured during setup.  The tasks therefore build
:py:data:`DEFAULT_MODEL`'s steps and swap in the configured model's in
``configure()``.
"""

from typing import TYPE_CHECKING, Dict

if TYPE_CHECKING:
    from polaris import Step, Task
    from polaris.config import PolarisConfigParser

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


def get_configured_model(config: 'PolarisConfigParser', default: str) -> str:
    """
    The ocean model a task's config says it is for.

    During setup, the ocean component resolves ``[ocean] model`` before any
    task is configured.  A config without that option, or with a model this
    workflow has no directory for, leaves the task with ``default``, the model
    it was built for.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        The task's config options.

    default : str
        The model the task's steps were built for.

    Returns
    -------
    str
        The model to build the task's steps for.
    """
    if not config.has_option('ocean', 'model'):
        return default
    model = config.get('ocean', 'model')
    return model if model in OCEAN_MODELS else default


def replace_steps(
    task: 'Task', old_steps: Dict[str, 'Step'], new_steps: Dict[str, 'Step']
) -> None:
    """
    Swap a task's steps from one model's set for another's.

    The two sets share their model-neutral steps, which are the same instances
    in both and are left alone.  Every other old step is removed before any
    new one is added, since the two models' steps have the same names.

    Parameters
    ----------
    task : polaris.Task
        The task to update.

    old_steps : dict of {str: polaris.Step}
        The steps the task was given, keyed by their symlink names.

    new_steps : dict of {str: polaris.Step}
        The steps to give the task instead, keyed the same way.
    """
    keep = {id(step) for step in new_steps.values()}
    for step in old_steps.values():
        if id(step) in keep:
            continue
        if task.steps.get(step.name) is step:
            task.remove_step(step)
    for symlink, step in new_steps.items():
        if step.name not in task.steps:
            task.add_step(step, symlink=symlink)
