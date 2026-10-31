from polaris.mesh.spherical.unified import UNIFIED_MESH_NAMES
from polaris.tasks.e3sm.init.component_inputs.assemble import TARGET_PRODUCTS
from polaris.tasks.e3sm.init.component_inputs.task import ComponentInputsTask


def add_component_inputs_tasks(component):
    """
    Add a task per unified mesh for staging E3SM component input files.

    Unified meshes only.  These stage the products an E3SM run needs from a
    mesh that took hours to build, which is not something a simple base mesh
    has.

    Parameters
    ----------
    component : polaris.Component
        the e3sm/init component that the tasks will be added to
    """
    for mesh_name in UNIFIED_MESH_NAMES:
        for target in sorted(TARGET_PRODUCTS):
            component.add_task(
                ComponentInputsTask(
                    component=component,
                    mesh_name=mesh_name,
                    target=target,
                )
            )
