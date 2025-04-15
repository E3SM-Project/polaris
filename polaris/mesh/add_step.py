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
    resolution to the ocean component (if one has not already been added)

    Parameters
    ----------
    component : polaris.Component
        The ocean component that the step will be added to

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
    else:
        prefix = 'qu'

    name = f'{prefix}_base_mesh_{res_str}'
    subdir = f'spherical/{prefix}/base_mesh/{res_str}'

    if subdir in component.steps:
        base_mesh = component.steps[subdir]

    else:
        if icosahedral:
            base_mesh = IcosahedralMeshStep(
                component=component,
                name=name,
                subdir=subdir,
                cell_width=resolution,
            )
        else:
            base_mesh = QuasiUniformSphericalMeshStep(
                component=component,
                name=name,
                subdir=subdir,
                cell_width=resolution,
            )

        # add default config options for spherical meshes
        config_filename = f'{base_mesh.name}.cfg'
        filepath = os.path.join(
            component.name, base_mesh.subdir, config_filename
        )
        config = PolarisConfigParser(filepath=filepath)
        config.add_from_package('polaris.mesh', 'spherical.cfg')
        base_mesh.set_shared_config(config)

        component.add_step(base_mesh)

    return base_mesh, res_str
