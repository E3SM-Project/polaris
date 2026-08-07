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

    mesh_dict = {
        'QU.240km': dict(mpaso_id=151209, omega_id=260720, ncells=7153),
        'EC30to60E2r2': dict(mpaso_id=200908, omega_id=260720, ncells=236853),
    }
    for mesh_name, mesh_info in mesh_dict.items():
        subdir = f'spherical/realistic_global/{mesh_name}'
        component.add_task(
            AnalysisMembers(
                component=component,
                subdir=subdir,
                mesh_name=mesh_name,
                mpaso_id=mesh_info['mpaso_id'],
                omega_id=mesh_info['omega_id'],
                ncells=mesh_info['ncells'],
            )
        )
