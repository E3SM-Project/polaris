"""
Staging of the input files an E3SM run needs for one MPAS mesh.

The products are built from what the upstream workflows already produce --
the culled meshes and index maps from ``e3sm/init``'s topography culling, and
the ocean initial condition from ``realistic_global``'s dynamic adjustment --
and staged into a tree laid out the way E3SM's ``inputdata`` expects.

Import direction
----------------

This package lives in ``e3sm/init`` and imports from
:py:mod:`polaris.tasks.ocean`, while
:py:mod:`polaris.tasks.ocean.realistic_global` imports from
:py:mod:`polaris.tasks.e3sm.init.topo.cull`.  That is acyclic only in one
direction, and it works because :py:mod:`polaris.tasks` fully imports
:py:mod:`polaris.tasks.e3sm.init` before any ``add_*_tasks`` function runs.

**Nothing under** :py:mod:`polaris.tasks.ocean` **may import this package.**
Reversing the direction is the kind of change a well-meaning refactor makes,
and it fails as an import error that is hard to place.
"""

from polaris.tasks.e3sm.init.component_inputs.assemble import (
    AssembleStep as AssembleStep,
)
from polaris.tasks.e3sm.init.component_inputs.base_mesh import (
    BaseMeshStep as BaseMeshStep,
)
from polaris.tasks.e3sm.init.component_inputs.scrip import (
    ScripStep as ScripStep,
)
from polaris.tasks.e3sm.init.component_inputs.steps import (
    get_component_inputs_steps as get_component_inputs_steps,
)
from polaris.tasks.e3sm.init.component_inputs.task import (
    ComponentInputsTask as ComponentInputsTask,
)
from polaris.tasks.e3sm.init.component_inputs.tasks import (
    add_component_inputs_tasks as add_component_inputs_tasks,
)
