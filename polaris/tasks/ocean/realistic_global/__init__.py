from polaris.config import PolarisConfigParser as PolarisConfigParser
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
    config_filename = 'realistic_global.cfg'
    # ncells 236853
    for mesh_name, mesh_id in [('QU240km', 151209), ('EC30to60E2r2', 200908)]:
        subdir = f'spherical/realistic_global/{mesh_name}'
        filepath = f'{subdir}/{config_filename}'
        config = PolarisConfigParser(filepath=filepath)
        component.add_task(
            AnalysisMembers(
                component=component,
                subdir=subdir,
                mesh_name=mesh,
                config=config,
                config_filename=config_filename,
                resolution_for_cell_count=240,
            )
        )

    component.add_task(Woa23(component=component))
