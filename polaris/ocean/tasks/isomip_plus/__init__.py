from typing import Dict, Union

from polaris.config import PolarisConfigParser
from polaris.ocean.resolution import resolution_to_subdir
from polaris.ocean.tasks.isomip_plus.cull_mesh import CullMesh
from polaris.ocean.tasks.isomip_plus.isomip_plus_test import IsomipPlusTest
from polaris.ocean.tasks.isomip_plus.planar_mesh import PlanarMesh
from polaris.ocean.tasks.isomip_plus.spherical_mesh import SphericalMesh
from polaris.ocean.tasks.isomip_plus.topo_map import TopoMap
from polaris.ocean.tasks.isomip_plus.topo_remap import TopoRemap


def add_isomip_plus_tasks(component, mesh_type):
    """
    Add tasks for different baroclinic channel tests to the ocean component

    component : polaris.ocean.Ocean
        the ocean component that the tasks will be added to

    mesh_type : {'planar', 'spherical'}
        The type of mesh
    """
    planar = (mesh_type == 'planar')
    for resolution in [4., 2., 1.]:
        mesh_name = resolution_to_subdir(resolution)
        resdir = f'{mesh_type}/isomip_plus/{mesh_name}'

        filepath = f'{resdir}/isomip_plus.cfg'
        config = PolarisConfigParser(filepath=filepath)
        if not planar:
            config.add_from_package('polaris.mesh', 'spherical.cfg')
            config.set('spherical_mesh', 'mpas_mesh_filename',
                       'base_mesh_without_xy.nc')

        config.add_from_package('polaris.ocean.tasks.isomip_plus',
                                'isomip_plus.cfg')

        base_mesh, topo_map_base, topo_remap_base, cull_mesh, \
            topo_map_culled, topo_remap_culled = \
            _get_shared_steps(mesh_type, resolution, mesh_name, resdir,
                              component, config)

        # ocean0 and ocean1 use the same topography
        topo_remap_culled['ocean0'] = topo_remap_culled['ocean1']

        for experiment in ['ocean0', 'ocean1', 'ocean2', 'ocean3', 'ocean4']:
            for vertical_coordinate in ['z-star']:
                task = IsomipPlusTest(
                    component=component,
                    resdir=resdir,
                    config=config,
                    resolution=resolution,
                    experiment=experiment,
                    vertical_coordinate=vertical_coordinate,
                    planar=planar,
                    base_mesh=base_mesh,
                    topo_map_base=topo_map_base,
                    topo_remap_base=topo_remap_base,
                    cull_mesh=cull_mesh,
                    topo_map_culled=topo_map_culled,
                    topo_remap_culled=topo_remap_culled[experiment])
                component.add_task(task)


def _get_shared_steps(mesh_type, resolution, mesh_name, resdir, component,
                      config):
    """ Get the shared steps for adding to tasks """

    subdir = f'{resdir}/base_mesh'
    base_mesh: Union[PlanarMesh, SphericalMesh, None] = None
    if mesh_type == 'planar':
        base_mesh = PlanarMesh(component=component,
                               resolution=resolution,
                               subdir=subdir,
                               config=config)
    else:
        base_mesh = SphericalMesh(component=component,
                                  cell_width=resolution,
                                  subdir=subdir)
        base_mesh.config = config

    subdir = f'{resdir}/topo/map_base'
    topo_map_base = TopoMap(component=component,
                            name='topo_map_base',
                            subdir=subdir,
                            config=config,
                            mesh_name=mesh_name,
                            mesh_step=base_mesh,
                            mesh_filename='base_mesh.nc')

    subdir = f'{resdir}/topo/remap_base'
    topo_remap_base = TopoRemap(component=component,
                                name='topo_remap_base',
                                subdir=subdir,
                                config=config,
                                topo_map=topo_map_base,
                                experiment='ocean1')

    subdir = f'{resdir}/topo/cull_mesh'
    cull_mesh = CullMesh(component=component,
                         subdir=subdir,
                         config=config,
                         base_mesh=base_mesh,
                         topo_remap=topo_remap_base)

    subdir = f'{resdir}/topo/map_culled'
    topo_map_culled = TopoMap(component=component,
                              name='topo_map_culled',
                              subdir=subdir,
                              config=config,
                              mesh_name=mesh_name,
                              mesh_step=cull_mesh,
                              mesh_filename='culled_mesh.nc')

    topo_remap_culled: Dict[str, TopoRemap] = dict()
    for experiment in ['ocean1', 'ocean2', 'ocean3', 'ocean4']:
        name = 'topo_remap_culled'
        subdir = f'{resdir}/topo/remap_culled/{experiment}'
        topo_remap_culled[experiment] = TopoRemap(component=component,
                                                  name=name,
                                                  subdir=subdir,
                                                  config=config,
                                                  topo_map=topo_map_culled,
                                                  experiment=experiment)

    return base_mesh, topo_map_base, topo_remap_base, cull_mesh, \
        topo_map_culled, topo_remap_culled
