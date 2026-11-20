from polaris.mesh.spherical.unified import UNIFIED_MESH_NAMES
from polaris.tasks.e3sm.init.component_inputs.assemble import OCEAN_PRODUCTS
from polaris.tasks.e3sm.init.component_inputs.task import ComponentInputsTask


def add_component_inputs_tasks(component):
    """
    Add tasks per unified mesh for staging E3SM component input files.

    Each mesh gets a task for its sea-ice products, and for each ocean model a
    task for its ocean products and one for both.

    Unified meshes only.  These stage the products an E3SM run needs from a
    mesh that took hours to build, which is not something a simple base mesh
    has.

    Parameters
    ----------
    component : polaris.Component
        the e3sm/init component that the tasks will be added to
    """
    for mesh_name in UNIFIED_MESH_NAMES:
        component.add_task(
            ComponentInputsTask(
                component=component, mesh_name=mesh_name, target='seaice'
            )
        )
        for model in OCEAN_PRODUCTS:
            for target in ['ocean', 'all']:
                component.add_task(
                    ComponentInputsTask(
                        component=component,
                        mesh_name=mesh_name,
                        target=target,
                        model=model,
                    )
                )
