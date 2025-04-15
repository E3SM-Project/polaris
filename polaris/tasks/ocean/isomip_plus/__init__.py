from typing import (
    Dict as Dict,
)
from typing import (
    Union as Union,
)

from polaris import Step as Step
from polaris.config import PolarisConfigParser as PolarisConfigParser
from polaris.resolution import resolution_to_string
from polaris.tasks.ocean.isomip_plus.isomip_plus_test import (
    IsomipPlusTest as IsomipPlusTest,
)
from polaris.tasks.ocean.isomip_plus.mesh import (
    CullMesh as CullMesh,
)
from polaris.tasks.ocean.isomip_plus.mesh import (
    PlanarMesh as PlanarMesh,
)
from polaris.tasks.ocean.isomip_plus.mesh import (
    SphericalMesh as SphericalMesh,
)
from polaris.tasks.ocean.isomip_plus.topo import (
    TopoMap as TopoMap,
)
from polaris.tasks.ocean.isomip_plus.topo import (
    TopoRemap as TopoRemap,
)
from polaris.tasks.ocean.isomip_plus.topo import (
    TopoScale as TopoScale,
)


def add_isomip_plus_tasks(component, mesh_type):
    """
    Add tasks for different baroclinic channel tests to the ocean component

    component : polaris.ocean.Ocean
        the ocean component that the tasks will be added to

    mesh_type : {'planar', 'spherical'}
        The type of mesh
    """
    planar = mesh_type == 'planar'
    for resolution in [4.0, 2.0, 1.0]:
        mesh_name = resolution_to_string(resolution)
        resdir = f'{mesh_type}/isomip_plus/{mesh_name}'

        filepath = f'{resdir}/isomip_plus_topo.cfg'
        config = PolarisConfigParser(filepath=filepath)
        if not planar:
            config.add_from_package('polaris.mesh', 'spherical.cfg')
            config.set(
                'spherical_mesh',
                'mpas_mesh_filename',
                'base_mesh_without_xy.nc',
            )

        config.add_from_package('polaris.remap', 'mapping.cfg')

        config.add_from_package(
            'polaris.tasks.ocean.isomip_plus', 'isomip_plus.cfg'
        )

        config.add_from_package(
            'polaris.tasks.ocean.isomip_plus', 'isomip_plus_topo.cfg'
        )

        shared_steps = _get_shared_steps(
            mesh_type, resolution, mesh_name, resdir, component, config
        )

        for experiment in [
            'ocean0',
            'ocean1',
            'ocean2',
            'ocean3',
            'ocean4',
            'inception',
            'wetting',
            'drying',
        ]:
            for vertical_coordinate in ['z-star']:
                task = IsomipPlusTest(
                    component=component,
                    resdir=resdir,
                    resolution=resolution,
                    experiment=experiment,
                    vertical_coordinate=vertical_coordinate,
                    planar=planar,
                    shared_steps=shared_steps[experiment],
                )
                component.add_task(task)


def _get_shared_steps(
    mesh_type, resolution, mesh_name, resdir, component, config
):
    """Get the shared steps for adding to tasks"""

    subdir = f'{resdir}/base_mesh'
    base_mesh: Union[PlanarMesh, SphericalMesh, None] = None
    if mesh_type == 'planar':
        base_mesh = PlanarMesh(
            component=component,
            resolution=resolution,
            subdir=subdir,
            config=config,
        )
    else:
        base_mesh = SphericalMesh(
            component=component, cell_width=resolution, subdir=subdir
        )
        base_mesh.set_shared_config(config, link='isomip_plus_topo.cfg')

    subdir = f'{resdir}/topo/map_base'
    # we remap the topography onto the base mesh without smoothing the
    # smoothing doesn't expand the domain.  We can use conservative
    # interpolation because we have already culled planar meshes to remove
    # periodicity
    topo_map_base = TopoMap(
        component=component,
        name='topo_map_base',
        subdir=subdir,
        config=config,
        mesh_name=mesh_name,
        mesh_step=base_mesh,
        mesh_filename='base_mesh.nc',
        method='conserve',
        smooth=False,
    )

    subdir = f'{resdir}/topo/remap_base'
    topo_remap_base = TopoRemap(
        component=component,
        name='topo_remap_base',
        subdir=subdir,
        config=config,
        topo_map=topo_map_base,
        experiment='ocean1',
    )

    subdir = f'{resdir}/topo/cull_mesh'
    cull_mesh = CullMesh(
        component=component,
        subdir=subdir,
        config=config,
        base_mesh=base_mesh,
        topo_remap=topo_remap_base,
    )

    subdir = f'{resdir}/topo/map_culled'
    # we remap the topography onto the culled mesh with smoothing, which
    # requires the conserve method
    topo_map_culled = TopoMap(
        component=component,
        name='topo_map_culled',
        subdir=subdir,
        config=config,
        mesh_name=mesh_name,
        mesh_step=cull_mesh,
        mesh_filename='culled_mesh.nc',
        method='conserve',
        smooth=True,
    )

    topo_remap_culled: Dict[str, TopoRemap] = dict()
    shared_steps: Dict[str, Dict[str, Step]] = dict()
    for experiment in ['ocean1', 'ocean2', 'ocean3', 'ocean4']:
        name = 'topo_remap_culled'
        subdir = f'{resdir}/topo/remap_culled/{experiment}'
        topo_remap_culled[experiment] = TopoRemap(
            component=component,
            name=name,
            subdir=subdir,
            config=config,
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
        subdir = f'{resdir}/topo/scale/{experiment}'
        topo_scale = TopoScale(
            component=component,
            subdir=subdir,
            config=config,
            topo_remap=topo_remap_culled['ocean1'],
            experiment=experiment,
        )
        shared_steps[experiment]['topo/scale'] = topo_scale
        shared_steps[experiment]['topo_final'] = topo_scale

    return shared_steps
