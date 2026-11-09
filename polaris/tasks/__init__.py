"""
The registry of Polaris components and their task groups

Nothing here imports a component or a task.  :py:data:`COMPONENTS` names the
module that defines each component, and each component's ``add_tasks``
module has a ``TASK_GROUPS`` dict naming the module and function that adds
each of its task groups.  :py:func:`get_components` imports only the
components and task groups it is asked for.
"""

import importlib
import weakref
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Iterable,
    List,
    Mapping,
    NamedTuple,
    Optional,
    Set,
)

if TYPE_CHECKING:
    from polaris import Component


class ComponentEntry(NamedTuple):
    """
    Where a component is defined

    Attributes
    ----------
    module : str
        The package that defines the component, which also has an
        ``add_tasks`` module

    instance : str
        The name of the component object in ``module``

    add_tasks : str
        The name of the function in ``<module>.add_tasks`` that adds the
        component's task groups
    """

    module: str
    instance: str
    add_tasks: str


class TaskGroup(NamedTuple):
    """
    Where a task group is defined

    Attributes
    ----------
    module : str
        The module with the function that adds the task group

    function : str
        The function, which takes the component as its ``component``
        keyword argument

    kwargs : dict, optional
        Any other keyword arguments to pass to the function
    """

    module: str
    function: str
    kwargs: Mapping[str, Any] = {}


# Add new components alphabetically.  A component's task groups are added
# after those of every component before it, which matters when one
# component's tasks share steps with another's: the mesh component's
# coastline tasks share steps with the e3sm/init component's.
COMPONENTS: Dict[str, ComponentEntry] = {
    'e3sm/init': ComponentEntry(
        'polaris.tasks.e3sm.init', 'e3sm_init', 'add_e3sm_init_tasks'
    ),
    'mesh': ComponentEntry('polaris.tasks.mesh', 'mesh', 'add_mesh_tasks'),
    'ocean': ComponentEntry('polaris.tasks.ocean', 'ocean', 'add_ocean_tasks'),
    'seaice': ComponentEntry(
        'polaris.tasks.seaice', 'seaice', 'add_seaice_tasks'
    ),
}

# the task groups that have been added to each component object
_groups_added: 'weakref.WeakKeyDictionary[Component, Set[str]]' = (
    weakref.WeakKeyDictionary()
)


def get_component_names() -> List[str]:
    """
    The names of the components, without importing any of them

    Returns
    -------
    names : list of str
        The component names, in the order tasks are listed
    """
    return list(COMPONENTS)


def get_task_group_names(component_name: str) -> List[str]:
    """
    The names of a component's task groups, in the order they are added

    Parameters
    ----------
    component_name : str
        The name of the component

    Returns
    -------
    names : list of str
        The names of the component's task groups
    """
    return list(_get_task_groups(component_name))


def get_components(
    add_tasks: bool = True,
    task_groups: Optional[Mapping[str, Iterable[str]]] = None,
) -> List['Component']:
    """
    Get the Polaris components

    Parameters
    ----------
    add_tasks : bool, optional
        Whether to add tasks to the components.  Building the tasks is by far
        the most expensive part of getting the components, so this can be
        ``False`` for callers that only need the components themselves (e.g.
        to add command-line arguments for each of them).

    task_groups : dict of list of str, optional
        The task groups to add for each component, with component names as
        keys.  A component that is not a key gets no task groups.  By default,
        every task group of every component is added.

    Returns
    -------
    components : list of polaris.Component
        The components, in the order of :py:data:`COMPONENTS`
    """
    components = [_get_component(name) for name in COMPONENTS]
    if not add_tasks:
        return components

    for component in components:
        name = component.name
        if task_groups is None:
            groups: Optional[List[str]] = None
        elif name in task_groups:
            groups = list(task_groups[name])
        else:
            continue
        add_task_groups(component, groups)

    return components


def add_task_groups(
    component: 'Component', groups: Optional[Iterable[str]] = None
) -> List[str]:
    """
    Add task groups to a component, skipping any already added

    Parameters
    ----------
    component : polaris.Component
        The component

    groups : list of str, optional
        The names of the task groups to add, all of them by default.  They
        are added in the order of the component's ``TASK_GROUPS``, whatever
        their order here.

    Returns
    -------
    added : list of str
        The task groups that were added by this call
    """
    all_groups = _get_task_groups(component.name)
    if groups is None:
        wanted = set(all_groups)
    else:
        wanted = set(groups)
        unknown = wanted - set(all_groups)
        if unknown:
            raise ValueError(
                f'Unknown task group(s) {sorted(unknown)} for component '
                f'{component.name}'
            )

    added_before = _groups_added.setdefault(component, set())
    added = list()
    for name, group in all_groups.items():
        if name not in wanted or name in added_before:
            continue
        module = importlib.import_module(group.module)
        function = getattr(module, group.function)
        function(component=component, **group.kwargs)
        added_before.add(name)
        added.append(name)
    return added


def _get_component(name: str) -> 'Component':
    entry = COMPONENTS[name]
    module = importlib.import_module(entry.module)
    return getattr(module, entry.instance)


def _get_task_groups(component_name: str) -> Dict[str, TaskGroup]:
    entry = COMPONENTS[component_name]
    module = importlib.import_module(f'{entry.module}.add_tasks')
    return module.TASK_GROUPS
