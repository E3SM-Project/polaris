import os
from typing import Dict

from polaris import Step
from polaris.config import PolarisConfigParser
from polaris.resolution import resolution_to_string
from polaris.tasks.ocean import ocean
from polaris.tasks.ocean.isomip_plus.mesh import CullMesh, PlanarMesh
from polaris.tasks.ocean.isomip_plus.topo import (
    TopoMap,
    TopoRemap,
    TopoScale,
)

#: The name of the config file shared by the mesh and topography steps
CONFIG_FILENAME = 'isomip_plus_topo.cfg'


def get_isomip_plus_mesh_steps(resolution, component=None):
    """
    Get the shared steps that make the ISOMIP+ mesh and topography at a
    given resolution

    The steps are created only once, so every caller gets the same
    instances.

    Parameters
    ----------
    resolution : float
        The resolution of the mesh in km

    component : polaris.tasks.ocean.Ocean, optional
        The ocean component the steps belong to, by default the one Polaris
        sets up tasks from

    Returns
    -------
    shared_steps : dict of str to dict of str to polaris.Step
        For each experiment, the steps that make its mesh and topography,
        keyed by logical step name.  ``topo/cull_mesh`` makes the culled mesh
        and ``topo_final`` the experiment's topography on it.

    config : polaris.config.PolarisConfigParser
        The shared config options for the steps
    """
    if component is None:
        component = ocean
    mesh_name = resolution_to_string(resolution)
    resdir = f'planar/isomip_plus/{mesh_name}'
    filepath = os.path.join(component.name, resdir, CONFIG_FILENAME)

    def create():
        config = PolarisConfigParser(filepath=filepath)
        config.add_from_package('polaris.remap', 'mapping.cfg')
        config.add_from_package(
            'polaris.tasks.ocean.isomip_plus', CONFIG_FILENAME
        )
        return config

    config = component.get_or_create_shared_config(
        filepath=filepath, create=create
    )

    def get_step(step_cls, subdir, **kwargs):
        return component.get_or_create_shared_step(
            step_cls=step_cls,
            subdir=f'{resdir}/{subdir}',
            config=config,
            config_filename=CONFIG_FILENAME,
            **kwargs,
        )

    base_mesh = get_step(PlanarMesh, 'base_mesh', resolution=resolution)

    # we remap the topography onto the base mesh without smoothing the
    # smoothing doesn't expand the domain.  We can use conservative
    # interpolation because we have already culled planar meshes to remove
    # periodicity
    topo_map_base = get_step(
        TopoMap,
        'topo/map_base',
        name='topo_map_base',
        mesh_name=mesh_name,
        mesh_step=base_mesh,
        mesh_filename='base_mesh.nc',
        method='conserve',
        smooth=False,
    )

    topo_remap_base = get_step(
        TopoRemap,
        'topo/remap_base',
        name='topo_remap_base',
        topo_map=topo_map_base,
        experiment='ocean1',
    )

    cull_mesh = get_step(
        CullMesh,
        'topo/cull_mesh',
        base_mesh=base_mesh,
        topo_remap=topo_remap_base,
    )

    # we remap the topography onto the culled mesh with smoothing, which
    # requires the conserve method
    topo_map_culled = get_step(
        TopoMap,
        'topo/map_culled',
        name='topo_map_culled',
        mesh_name=mesh_name,
        mesh_step=cull_mesh,
        mesh_filename='culled_mesh.nc',
        method='conserve',
        smooth=True,
    )

    topo_remap_culled: Dict[str, Step] = dict()
    shared_steps: Dict[str, Dict[str, Step]] = dict()
    for experiment in ['ocean1', 'ocean2']:
        topo_remap_culled[experiment] = get_step(
            TopoRemap,
            f'topo/remap_culled/{experiment}',
            name='topo_remap_culled',
            topo_map=topo_map_culled,
            experiment=experiment,
        )

        shared_steps[experiment] = {
            'base_mesh': base_mesh,
            'topo/map_base': topo_map_base,
            'topo/remap_base': topo_remap_base,
            'topo/cull_mesh': cull_mesh,
            'topo/map_culled': topo_map_culled,
            'topo/remap_culled': topo_remap_culled[experiment],
            'topo_final': topo_remap_culled[experiment],
        }

    # ocean0 and ocean1 use the same topography
    shared_steps['ocean0'] = shared_steps['ocean1']

    for experiment in ['inception', 'wetting', 'drying']:
        shared_steps[experiment] = dict(shared_steps['ocean1'])
        topo_scale = get_step(
            TopoScale,
            f'topo/scale/{experiment}',
            topo_remap=topo_remap_culled['ocean1'],
            experiment=experiment,
        )
        shared_steps[experiment]['topo/scale'] = topo_scale
        shared_steps[experiment]['topo_final'] = topo_scale

    return shared_steps, config
