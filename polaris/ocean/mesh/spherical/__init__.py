import os
from typing import Union

from polaris.config import PolarisConfigParser
from polaris.mesh.spherical import (
    IcosahedralMeshStep,
    QuasiUniformSphericalMeshStep,
    SphericalBaseStep,
)
from polaris.ocean.resolution import resolution_to_subdir


def add_spherical_base_mesh_step(component, prefix, resolution=None,
                                 resolutions=None):
    """
    Add a shared step for creating spherical base mesh with the given
    resolution to the ocean component (if one has not already been added)

    Parameters
    ----------
    component : polaris.Component
        The ocean component that the step will be added to

    prefix : str
        A prefix describing the typ of mesh (e.g. 'qu', 'icos', 'rrs')

    resolution : float, optional
        The resolution in km of the mesh if it is approximately uniform. One of
        ``resolution`` or ``resolutions`` must be given.

    resolutions : str, optional
        the range of resolutions if nonuniform (e.g.`6to18km'). One of
        ``resolution`` or ``resolutions`` must be given.

    Returns
    -------
    base_mesh : polaris.Step
        The base mesh step

    mesh_name : str
        The name of the mesh (e.g. '240km')
    """
    if resolutions is None and resolution is None:
        raise ValueError('One of resolution or resolutions must be given.')

    if resolutions is not None and resolution is not None:
        raise ValueError('Only one of resolution or resolutions should be '
                         'given.')

    if resolution is not None:
        mesh_name = resolution_to_subdir(resolution)
    else:
        mesh_name = resolutions

    name = f'{prefix}_base_mesh_{mesh_name}'
    subdir = f'spherical/{prefix}/base_mesh/{mesh_name}'

    if subdir in component.steps:
        base_mesh = component.steps[subdir]

    else:
        if resolution is not None:
            base_mesh = _get_uniform_base_mesh(prefix, component, name, subdir,
                                               resolution)
        else:
            base_mesh = _get_nonuniform_base_mesh(prefix, component, name,
                                                  subdir, resolutions)

        # add default config options for spherical meshes
        config_filename = f'{base_mesh.name}.cfg'
        filepath = os.path.join(base_mesh.subdir, config_filename)
        config = PolarisConfigParser(filepath=filepath)
        config.add_from_package('polaris.mesh', 'spherical.cfg')
        base_mesh.set_shared_config(config)

        component.add_step(base_mesh)

    return base_mesh, mesh_name


def _get_uniform_base_mesh(prefix, component, name, subdir, resolution):
    base_mesh: Union[SphericalBaseStep, None] = None
    if prefix == 'icos':
        base_mesh = IcosahedralMeshStep(
            component=component, name=name, subdir=subdir,
            cell_width=resolution)
    elif prefix == 'qu':
        base_mesh = QuasiUniformSphericalMeshStep(
            component=component, name=name, subdir=subdir,
            cell_width=resolution)
    else:
        raise ValueError(f'Unexpected prefix {prefix} for a mesh with uniform '
                         f'resolution')

    return base_mesh


def _get_nonuniform_base_mesh(prefix, component, name, subdir, resolutions):
    raise ValueError(f'Unexpected prefix {prefix} for non-uniform mesh')
