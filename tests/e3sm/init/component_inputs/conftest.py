import pytest

from polaris.tasks.e3sm.init import e3sm_init
from polaris.tasks.mesh import mesh as mesh_component
from polaris.tasks.ocean import ocean


@pytest.fixture(autouse=True)
def _empty_shared_components():
    """
    Leave the shared components as empty as each test found them.

    The tests here build steps in the module-level components, and a step
    left there is reachable from any step pickled later in the session, so a
    test elsewhere that counts what a pickle holds would count these too.
    """
    yield
    for component in [e3sm_init, mesh_component, ocean]:
        component.tasks.clear()
        component.steps.clear()
        component.configs.clear()
