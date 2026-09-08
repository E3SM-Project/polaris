"""
Carrying a placement from the scheduler to the process that runs the step.

The scheduler decides which part of the allocation a step gets, and the step
runs in a process of its own, so the decision has to cross a process
boundary.  It travels in the environment rather than in the step's pickle,
because the pickle is written once at setup and a step shared between tasks
is scheduled once, while a placement belongs to one run of one step.

A placement that is silently lost would be the worst outcome available here:
the step would run on the whole allocation, look like it worked, and
oversubscribe the machine beside whatever else was running.  So a value that
cannot be read raises rather than being treated as "no placement".
"""

import json
import os
from typing import Any, Dict, Optional

from mache.parallel import ResourcePlacement

# the environment variable a step's process reads its placement from
PLACEMENT_VAR = 'POLARIS_PLACEMENT'


def placement_to_env(placement: Optional[ResourcePlacement]) -> Dict[str, str]:
    """
    Describe a placement as environment variables for a step's process.

    Parameters
    ----------
    placement : mache.parallel.ResourcePlacement or None
        The part of the allocation the step is confined to, or ``None`` to
        run it as ``polaris serial`` always has

    Returns
    -------
    environ : dict of str
        Variables to add to the step process's environment, empty when
        there is no placement to carry
    """
    if placement is None:
        return {}

    value: Dict[str, Any] = {
        'nodes': list(placement.nodes),
        'cores': [list(node_cores) for node_cores in placement.cores],
        'gpus': placement.gpus,
    }
    if placement.gpu_ids is not None:
        value['gpu_ids'] = list(placement.gpu_ids)
    return {PLACEMENT_VAR: json.dumps(value)}


def placement_from_env(environ=None) -> Optional[ResourcePlacement]:
    """
    Read the placement a step's process was given, if it was given one.

    Parameters
    ----------
    environ : dict, optional
        The environment to read, defaulting to this process's own

    Returns
    -------
    placement : mache.parallel.ResourcePlacement or None
        What the scheduler assigned, or ``None`` when nothing did

    Raises
    ------
    ValueError
        If the variable is set to something that cannot be read as a
        placement.  Running unplaced instead would oversubscribe the
        machine while appearing to work.
    """
    environ = os.environ if environ is None else environ
    raw = environ.get(PLACEMENT_VAR)
    if not raw:
        return None

    try:
        value = json.loads(raw)
        placement = ResourcePlacement(
            nodes=tuple(value['nodes']),
            cores=tuple(tuple(cores) for cores in value['cores']),
            gpus=value.get('gpus', 0),
            gpu_ids=(
                None
                if value.get('gpu_ids') is None
                else tuple(value['gpu_ids'])
            ),
        )
    except (
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exception:
        raise ValueError(
            f'{PLACEMENT_VAR} is set but could not be read as a placement, '
            f'so this step does not know which part of the allocation it '
            f'has. Refusing to run it on all of it.\n  {PLACEMENT_VAR}={raw}'
        ) from exception

    return placement
