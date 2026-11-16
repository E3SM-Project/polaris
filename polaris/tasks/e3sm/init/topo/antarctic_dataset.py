"""
The choice of Antarctic topography dataset.

The ``[remap_topography] antarctic_dataset`` config option selects which
combined topography is remapped to an MPAS mesh and which the WOA23
extrapolation uses.  Each dataset has its own combine steps, with their own
paths and cached outputs, and so does the WOA23 extrapolation, so the choice
decides which steps a task has.  Polaris builds tasks before it reads a
user's config file, so the steps start out with the default dataset, and the
``configure()`` methods of the e3sm/init and ocean components swap in the
steps for the dataset in the user's config before anything is set up.  The
option can therefore only be set in a user config file passed to
``polaris setup``.
"""

from polaris.step import Step
from polaris.tasks.e3sm.init.topo.combine.files import (
    ANTARCTIC,
    ANTARCTIC_DATASETS,
)
from polaris.tasks.e3sm.init.topo.combine.step import CombineStep
from polaris.tasks.e3sm.init.topo.combine.steps import (
    get_cubed_sphere_topo_steps,
)

#: The section and option holding the Antarctic dataset
DATASET_SECTION = 'remap_topography'
DATASET_OPTION = 'antarctic_dataset'


def get_antarctic_dataset(config):
    """
    Get the Antarctic topography dataset from a config.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        The config, which may hold the dataset in its
        ``[remap_topography]`` section.  A config without it gets the
        default dataset.

    Returns
    -------
    antarctic_dataset : str
        The dataset, one of ``ANTARCTIC_DATASETS``
    """
    antarctic_dataset = config.get(
        DATASET_SECTION, DATASET_OPTION, fallback=ANTARCTIC
    )
    if antarctic_dataset not in ANTARCTIC_DATASETS:
        valid = ', '.join(ANTARCTIC_DATASETS)
        raise ValueError(
            f'Unexpected [{DATASET_SECTION}] {DATASET_OPTION} '
            f'{antarctic_dataset!r}. Valid options are: {valid}'
        )
    return antarctic_dataset


def add_antarctic_dataset_option(step):
    """
    Declare the Antarctic dataset a setup-only option of a step that uses
    combined topography.

    Parameters
    ----------
    step : polaris.Step
        A step with a ``combine_topo_step`` attribute
    """
    step.add_setup_only_option(DATASET_SECTION, DATASET_OPTION)


def check_combine_topo_dataset(step):
    """
    Check, at setup, that a step's combined topography comes from the
    Antarctic dataset in its config.

    Parameters
    ----------
    step : polaris.Step
        A step with a ``combine_topo_step`` attribute

    Raises
    ------
    ValueError
        If the combine step uses another dataset, which means the swap in
        :py:func:`select_antarctic_dataset` did not reach this step
    """
    antarctic_dataset = get_antarctic_dataset(step.config)
    combine_dataset = step.combine_topo_step.antarctic_dataset
    if combine_dataset != antarctic_dataset:
        raise ValueError(
            f'Step {step.path} is set up with combined topography from '
            f'{combine_dataset}, but its config asks for '
            f'{antarctic_dataset}.'
        )


def select_antarctic_dataset(component, steps, antarctic_dataset):
    """
    Point steps that use combined topography on a cubed-sphere grid at the
    combine steps for an Antarctic dataset, replacing the combine steps in
    every task that has them.

    Parameters
    ----------
    component : polaris.Component
        The e3sm/init component, which owns the combine steps

    steps : list of polaris.Step
        The steps to check.  Those with a cubed-sphere ``combine_topo_step``
        from another dataset are given the matching one for
        ``antarctic_dataset``.  Steps that use latitude-longitude combined
        topography belong to other components, which make their own
        replacements.

    antarctic_dataset : str
        The Antarctic dataset, one of ``ANTARCTIC_DATASETS``
    """
    replacements: list[tuple[Step, Step]] = list()
    replaced = set()
    for step in steps:
        old = getattr(step, 'combine_topo_step', None)
        if (
            old is None
            or old.antarctic_dataset == antarctic_dataset
            or id(old) in replaced
            or old.config.get('combine_topo', 'target_grid') != 'cubed_sphere'
        ):
            continue
        new = _get_matching_combine_step(component, old, antarctic_dataset)
        replacements.extend(get_combine_step_replacements(old, new))
        replaced.add(id(old))
    replace_steps(replacements, steps)


def get_combine_step_replacements(old, new):
    """
    Get the pairs of steps to replace when one combine step replaces another:
    the combine steps and the steps that prepare for them and make weights

    Parameters
    ----------
    old : polaris.tasks.e3sm.init.topo.combine.CombineStep
        The combine step to replace

    new : polaris.tasks.e3sm.init.topo.combine.CombineStep
        The combine step to replace it with

    Returns
    -------
    replacements : list of tuple of polaris.Step
        The pairs of old and new steps
    """
    return list(zip(_with_upstream(old), _with_upstream(new), strict=True))


def replace_steps(replacements, steps):
    """
    Replace steps in every task that has them, and in the attributes of other
    steps that refer to them.

    This is for steps whose identity depends on a setup-only config option,
    which Polaris builds with the default before it reads a user's config
    file.  It must happen before the steps are set up.  A replaced step may
    be referred to by attributes that other steps use in ``setup()``, but it
    may not be a dependency (added with ``add_dependency()``) of another
    step, since the input file that carries a dependency is fixed when it is
    added.

    Parameters
    ----------
    replacements : list of tuple of polaris.Step
        The pairs of old and new steps

    steps : list of polaris.Step
        The steps whose attributes may refer to the old steps
    """
    new_steps = {id(old): new for old, new in replacements}
    for old, new in replacements:
        for task in list(old.tasks.values()):
            _replace_step(task, old, new)
    for step in steps:
        if id(step) in new_steps:
            # a step being replaced keeps its own references
            continue
        for dependency in step.dependencies.values():
            if id(dependency) in new_steps:
                raise ValueError(
                    f'Step {step.path} depends on {dependency.path}, '
                    f'which cannot be replaced after it has been added as a '
                    f'dependency.'
                )
        for name, value in list(vars(step).items()):
            if id(value) in new_steps:
                setattr(step, name, new_steps[id(value)])


def _get_matching_combine_step(component, old, antarctic_dataset):
    """
    Get the combine step for a dataset on the same cubed-sphere grid as
    another combine step
    """
    resolution = old.config.getint('combine_topo', 'resolution_cubedsphere')
    steps, _ = get_cubed_sphere_topo_steps(
        component=component,
        resolution=resolution,
        antarctic_dataset=antarctic_dataset,
    )
    name = CombineStep.get_name(
        'cubed_sphere', f'ne{resolution}', antarctic_dataset
    )
    return steps[name]


def _with_upstream(combine_step):
    """A combine step and the steps that prepare for it and make weights"""
    return [
        combine_step.prepare_step,
        combine_step.weights_step,
        combine_step,
    ]


def _replace_step(task, old, new):
    """
    Replace a step in a task with another, keeping its place, its symlink,
    whether it runs by default and whether the task keeps it free-running
    """
    if old.name not in task.steps:
        return
    if old.subdir in task.free_running_steps:
        task.free_running_steps.discard(old.subdir)
        task.free_running_steps.add(new.subdir)
    symlink = task.step_symlinks.get(old.name)
    names = list(task.steps)
    index = names.index(old.name)
    run_by_default = old.name in task.steps_to_run
    run_index = task.steps_to_run.index(old.name) if run_by_default else None

    task.remove_step(old)
    task.add_step(new, symlink=symlink, run_by_default=run_by_default)

    # keep the new step where the old one was, so that it still runs before
    # the steps that use its outputs
    steps = list(task.steps.items())
    steps.insert(index, steps.pop())
    task.steps.clear()
    task.steps.update(steps)
    if run_index is not None:
        task.steps_to_run.remove(new.name)
        task.steps_to_run.insert(run_index, new.name)
