import os

from polaris.config import PolarisConfigParser
from polaris.mesh.spherical import (
    IcosahedralMeshStep,
    QuasiUniformSphericalMeshStep,
)
from polaris.resolution import resolution_to_string
from polaris.tasks.mesh import mesh as mesh_component


def add_uniform_spherical_base_mesh_step(resolution, icosahedral):
    """
    Add a shared step for creating spherical base mesh with the given
    resolution to the mesh component (if one has not already been added)

    Parameters
    ----------
    resolution : float
        The resolution in km of the mesh

    icosahedral : bool
        Whether the mesh is a subdivided icosahedral mesh, as opposed to
        a quasi-uniform

    Returns
    -------
    base_mesh : polaris.Step
        The base mesh step

    res_str : str
        The resolution of the mesh as a string (e.g. '240km')
    """
    component = mesh_component
    res_str = resolution_to_string(resolution)

    if icosahedral:
        prefix = 'icos'
        mesh_name = f'Icos{res_str}'
    else:
        prefix = 'qu'
        mesh_name = f'QU{res_str}'

    name = f'{prefix}_base_mesh_{res_str}'
    subdir = f'spherical/{prefix}/base_mesh/{res_str}'

    config_filename = f'{name}.cfg'

    filepath = os.path.join(component.name, subdir, config_filename)
    config = PolarisConfigParser(filepath=filepath)
    config.add_from_package('polaris.mesh', 'spherical.cfg')

    if icosahedral:
        base_mesh = component.get_or_create_shared_step(
            step_cls=IcosahedralMeshStep,
            subdir=subdir,
            config=config,
            config_filename=config_filename,
            name=name,
            cell_width=resolution,
            mesh_name=mesh_name,
        )
    else:
        base_mesh = component.get_or_create_shared_step(
            step_cls=QuasiUniformSphericalMeshStep,
            subdir=subdir,
            config=config,
            config_filename=config_filename,
            name=name,
            cell_width=resolution,
            mesh_name=mesh_name,
        )

    return base_mesh, res_str
