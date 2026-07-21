from polaris.tasks.ocean.realistic_global.analysis_members import (
    AnalysisMembers as AnalysisMembers,
)
from polaris.tasks.ocean.realistic_global.hydrography.woa23 import (
    Woa23 as Woa23,
)


def add_realistic_global_tasks(component):
    """
    Add tasks for realistic global ocean preprocessing and initialization.

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        The ocean component to which the tasks will be added.
    """
    component.add_task(Woa23(component=component))

    # ncells 236853
    mesh_list = [('QU240km', 151209, 260720), ('EC30to60E2r2', 200908, 260720)]
    for mesh_name, mpaso_id, omega_id in mesh_list:
        subdir = f'spherical/realistic_global/{mesh_name}'
        component.add_task(
            AnalysisMembers(
                component=component,
                subdir=subdir,
                mesh_name=mesh_name,
                mpaso_id=mpaso_id,
                omega_id=omega_id,
                resolution_for_cell_count=240,
            )
        )
