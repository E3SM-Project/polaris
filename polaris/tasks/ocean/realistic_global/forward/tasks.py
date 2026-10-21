from typing import Any, Dict

from polaris.mesh.base import get_base_mesh_step_names
from polaris.mesh.spherical.unified import UNIFIED_MESH_NAMES
from polaris.tasks.ocean.realistic_global.init.steps import (
    get_realistic_init_steps,
)
from polaris.tasks.ocean.realistic_global.mesh_info import (
    estimate_ocean_cell_count,
    min_res_for_mesh,
)

from .initial_condition import DatabaseInitialCondition, StepInitialCondition
from .task import TIME_INTEGRATORS, RealisticGlobalForward


def add_realistic_global_forward_tasks(component):
    """
    Add :py:class:`.RealisticGlobalForward` tasks for every supported base and
    unified MPAS mesh, one for each of ``TIME_INTEGRATORS``.

    The mesh list matches the one used by
    :py:func:`polaris.tasks.ocean.realistic_global.init.tasks.add_realistic_global_init_tasks`,
    so that every mesh with a realistic initial condition also gets a
    corresponding forward task.

    The target ocean model is not fixed at registration time; it is resolved
    from the ``[ocean] model`` config option during component setup.

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        The ocean component to add the tasks to.
    """
    mesh_names = list(get_base_mesh_step_names()) + list(UNIFIED_MESH_NAMES)
    for mesh_name in mesh_names:
        init_steps, _ = get_realistic_init_steps(
            component=component, mesh_name=mesh_name, include_viz=False
        )
        init_condition = StepInitialCondition(
            init_steps['initial_state'],
            min_res=min_res_for_mesh(mesh_name),
            approx_cell_count=estimate_ocean_cell_count(mesh_name),
            forcing_step=init_steps['forcing'],
        )
        for time_integrator in TIME_INTEGRATORS:
            component.add_task(
                RealisticGlobalForward(
                    component=component,
                    mesh_name=mesh_name,
                    init_condition=init_condition,
                    init_steps=init_steps,
                    time_integrator=time_integrator,
                )
            )


# Meshes with a cached initial condition in the Polaris input-file database.
# These are not Polaris-built meshes and there is no init workflow for
# them; the initial conditions were converted from existing E3SM ones by
# ``utils/omega/convert_mpaso_ic_to_omega.py`` and uploaded, and the ids and
# database names below are what is on the server.
#
# ``min_res`` is the measured minimum ``dcEdge`` rather than the nominal
# resolution in the mesh name -- 22.5 km for a mesh called 30-to-60 km --
# but it goes unused while the per-mesh configs give an explicit time step.
#
# The keys are Polaris's names for these E3SM meshes, prefixed with ``e3sm-``
# to keep them apart from the meshes Polaris builds; ``database_name`` is the
# name the files on the server carry.
CACHED_MESHES: Dict[str, Dict[str, Any]] = {
    'e3sm-qu240': dict(
        database_name='QU.240km',
        mpaso_id=151209,
        omega_id=260807,
        min_res=240.0,
        cell_count=7153,
    ),
    'e3sm-ec30to60e2r2': dict(
        database_name='EC30to60E2r2',
        mpaso_id=200908,
        omega_id=260807,
        min_res=22.5,
        cell_count=236853,
    ),
}


def get_cached_initial_condition(mesh_name):
    """
    The initial condition of a cached mesh, from the Polaris input-file
    database

    Parameters
    ----------
    mesh_name : str
        A key of ``CACHED_MESHES``, e.g. ``e3sm-qu240``

    Returns
    -------
    init_condition : DatabaseInitialCondition
        The source of the model input files
    """
    mesh_info = CACHED_MESHES[mesh_name]
    return DatabaseInitialCondition(
        mesh_name=mesh_info['database_name'],
        mpaso_id=mesh_info['mpaso_id'],
        omega_id=mesh_info['omega_id'],
        min_res=mesh_info['min_res'],
        approx_cell_count=mesh_info['cell_count'],
    )


def add_realistic_global_cached_forward_tasks(component):
    """
    Add :py:class:`.RealisticGlobalForward` tasks that run from a cached
    initial condition in the Polaris input-file database, one for each of
    ``TIME_INTEGRATORS``.

    The cached initial conditions are E3SM's, for E3SM meshes, converted for
    Omega.  They let Omega run realistic global configurations, and be
    compared with MPAS-Ocean, before Polaris could build its own initial
    conditions, and these tasks are temporary.  They download an initial
    condition instead of building one, so unlike
    :py:func:`add_realistic_global_forward_tasks` they can run without first
    remapping WOA23 and culling topography, which is what makes them usable in
    a PR suite.

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        The ocean component to add the tasks to.
    """
    for mesh_name in CACHED_MESHES:
        init_condition = get_cached_initial_condition(mesh_name)
        for time_integrator in TIME_INTEGRATORS:
            component.add_task(
                RealisticGlobalForward(
                    component=component,
                    mesh_name=mesh_name,
                    init_condition=init_condition,
                    subdir_name='cached_forward',
                    time_integrator=time_integrator,
                )
            )
