from polaris.mesh.spherical import (
    IcosahedralMeshStep,
    QuasiUniformSphericalMeshStep,
)
from polaris.ocean.resolution import resolution_to_subdir


def add_spherical_base_mesh_step(component, resolution, icosahedral):
    """
    Add a shared step for creating spherical base mesh with the given
    resolution to the ocean component (if one has not already been added)

    Parameters
    ----------
    component : polaris.Component
        The ocean component that the step will be added to

    resolution : float
        The resolution in km of the mesh

    icosahedral : bool
        Whether the mesh is a subdivided icosahedral mesh, as opposed to

    Returns
    -------
    base_mesh : polaris.Step
        The base mesh step

    mesh_name : str
        The name of the mesh (e.g. '240km')
    """
    mesh_name = resolution_to_subdir(resolution)

    if icosahedral:
        prefix = 'icos'
    else:
        prefix = 'qu'

    name = f'{prefix}_base_mesh_{mesh_name}'
    subdir = f'spherical/{prefix}/base_mesh/{mesh_name}'

    if subdir in component.steps:
        base_mesh = component.steps[subdir]

    else:
        if icosahedral:
            base_mesh = IcosahedralMeshStep(
                component=component, name=name, subdir=subdir,
                cell_width=resolution)
        else:
            base_mesh = QuasiUniformSphericalMeshStep(
                component=component, name=name, subdir=subdir,
                cell_width=resolution)

        component.add_step(base_mesh)

    return base_mesh, mesh_name
