import os

from polaris.config import PolarisConfigParser
from polaris.mesh.spherical import (
    IcosahedralMeshStep,
    QuasiUniformSphericalMeshStep,
)
from polaris.resolution import (
    resolution_to_string,
    resolution_to_string_and_units,
)
from polaris.tasks.mesh import mesh as mesh_component

MESH_CLASSES = {
    'icos': IcosahedralMeshStep,
    'qu': QuasiUniformSphericalMeshStep,
}

MESH_NAME_PREFIXES = {
    'icos': 'Icos',
    'qu': 'QU',
}


def add_spherical_base_mesh_step(prefix, min_res, max_res=None):
    """
    Add a shared step for creating spherical base mesh with the given
    resolution to the mesh component (if one has not already been added)

    Parameters
    ----------
    prefix : str
        The prefix for the mesh type (e.g. 'icos', 'qu', 'so')

    min_res : float
        The minimum resolution in km of the mesh

    max_res : float, optional
        The maximum resolution in km of the mesh. If not provided, it will
        default to the minimum resolution.

    Returns
    -------
    base_mesh : polaris.Step
        The base mesh step

    res_str : str
        The resolution of the mesh as a string (e.g. '240km' or '12to30km)
    """
    component = mesh_component
    if max_res is None:
        res_str = resolution_to_string(min_res)
        max_res = min_res
    else:
        min_str, min_units = resolution_to_string_and_units(min_res)
        max_str, max_units = resolution_to_string_and_units(max_res)
        if min_units == max_units:
            min_units = ''
        res_str = f'{min_str}{min_units}to{max_str}{max_units}'

    mesh_name = f'{prefix}{res_str}'
    prefix_lower = prefix.lower()

    name = f'{prefix_lower}_base_mesh_{res_str}'
    subdir = f'spherical/{prefix_lower}/base_mesh/{res_str}'

    config_filename = f'{name}.cfg'

    filepath = os.path.join(component.name, subdir, config_filename)
    config = PolarisConfigParser(filepath=filepath)
    config.add_from_package('polaris.mesh', 'spherical.cfg')
    config.set('spherical_mesh', 'prefix', MESH_NAME_PREFIXES[prefix])
    config.set('spherical_mesh', 'min_cell_width', f'{min_res:g}')
    config.set('spherical_mesh', 'max_cell_width', f'{max_res:g}')

    kwargs = {
        'step_cls': MESH_CLASSES[prefix],
        'subdir': subdir,
        'config': config,
        'config_filename': config_filename,
        'name': name,
        'mesh_name': mesh_name,
    }
    if prefix in ['Icos', 'QU']:
        kwargs['cell_width'] = min_res
    else:
        kwargs['min_cell_width'] = min_res
        kwargs['max_cell_width'] = max_res

    base_mesh = component.get_or_create_shared_step(**kwargs)

    return base_mesh, res_str
