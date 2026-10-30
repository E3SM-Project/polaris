import os

from polaris.config import PolarisConfigParser
from polaris.step import Step
from polaris.tasks.e3sm.init import e3sm_init
from polaris.tasks.e3sm.init.misomip.maps import MAPS, MapStep
from polaris.tasks.e3sm.init.misomip.mesh import (
    LandiceMeshStep,
    OceanMeshStep,
)
from polaris.tasks.mesh.planar.mismip_plus import get_mismip_plus_mesh_steps
from polaris.tasks.ocean.isomip_plus import get_isomip_plus_mesh_steps

#: The pairs of ocean and MALI meshes, with each one's resolution in km
MESH_PAIRS = {
    'misomip-o4km-li1km': {'ocean': 4.0, 'landice': 1.0},
    'misomip-o2km-li1km': {'ocean': 2.0, 'landice': 1.0},
}

#: The name of the config file shared by the steps of a pair of meshes
CONFIG_FILENAME = 'misomip.cfg'

CONFIG_PACKAGE = 'polaris.tasks.e3sm.init.misomip'


def get_misomip_mesh_steps(mesh_name):
    """
    Get the shared steps that give a pair of MISOMIP meshes latitude and
    longitude, SCRIP files and the maps between them

    Parameters
    ----------
    mesh_name : str
        The name of the pair of meshes, one of :py:data:`MESH_PAIRS`

    Returns
    -------
    steps : dict of str to polaris.Step
        The steps, including the ISOMIP+ and MISMIP+ steps that make the
        meshes, keyed by their suggested symlink names

    config : polaris.config.PolarisConfigParser
        The shared config options for the steps of the pair
    """
    if mesh_name not in MESH_PAIRS:
        raise ValueError(
            f'Unknown MISOMIP mesh {mesh_name!r}.  Expected one of '
            f'{", ".join(MESH_PAIRS)}.'
        )
    resolutions = MESH_PAIRS[mesh_name]
    config = _get_config(mesh_name)
    steps: dict[str, Step] = dict()

    isomip_plus_steps, _ = get_isomip_plus_mesh_steps(resolutions['ocean'])
    for name in [
        'base_mesh',
        'topo/map_base',
        'topo/remap_base',
        'topo/cull_mesh',
    ]:
        steps[f'isomip_plus/{name}'] = isomip_plus_steps['ocean1'][name]

    mismip_plus_steps, _ = get_mismip_plus_mesh_steps(resolutions['landice'])
    steps['mismip_plus/mesh'] = mismip_plus_steps['mesh']

    def get_step(step_cls, subdir, **kwargs):
        return e3sm_init.get_or_create_shared_step(
            step_cls=step_cls,
            subdir=os.path.join(mesh_name, subdir),
            config=config,
            config_filename=CONFIG_FILENAME,
            **kwargs,
        )

    mesh_steps = {
        'ocean': get_step(
            OceanMeshStep,
            'ocean_mesh',
            cull_mesh_step=steps['isomip_plus/topo/cull_mesh'],
        ),
        'landice': get_step(
            LandiceMeshStep,
            'landice_mesh',
            mesh_step=steps['mismip_plus/mesh'],
        ),
    }
    steps['ocean_mesh'] = mesh_steps['ocean']
    steps['landice_mesh'] = mesh_steps['landice']

    for map_name in MAPS:
        steps[f'maps/{map_name}'] = get_step(
            MapStep,
            os.path.join('maps', map_name),
            map_name=map_name,
            mesh_steps=mesh_steps,
        )

    return steps, config


def _get_config(mesh_name):
    """
    Get or create the shared config for the steps of a pair of meshes
    """
    filepath = os.path.join(e3sm_init.name, mesh_name, CONFIG_FILENAME)

    def create():
        config = PolarisConfigParser(filepath=filepath)
        config.add_from_package('polaris.remap', 'mapping.cfg')
        config.add_from_package(CONFIG_PACKAGE, CONFIG_FILENAME)
        config.add_from_package(CONFIG_PACKAGE, f'{mesh_name}.cfg')
        return config

    return e3sm_init.get_or_create_shared_config(
        filepath=filepath, create=create
    )
