import os
from typing import (
    Dict as Dict,
)
from typing import (
    List as List,
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
from polaris.tasks.ocean.isomip_plus.steps import (
    get_isomip_plus_mesh_steps as get_isomip_plus_mesh_steps,
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

# The ISOMIP+ experiments, each of which has a default task
EXPERIMENTS = ['ocean0', 'ocean1', 'ocean2', 'inception', 'wetting', 'drying']

# Variants of the default tasks, with the experiments each applies to.  A
# variant adds a level to the task path and its own config file,
# ``<variant>.cfg`` in this package.
VARIANTS: Dict[str, List[str]] = {
    # the COM physics of the protocol, for comparison with published results
    'com': ['ocean0', 'ocean1', 'ocean2'],
}


def add_isomip_plus_tasks(component):
    """
    Add ISOMIP+ tasks to the ocean component

    component : polaris.tasks.ocean.Ocean
        the ocean component that the tasks will be added to
    """
    for resolution in [4.0, 2.0, 1.0]:
        mesh_name = resolution_to_string(resolution)
        resdir = f'planar/isomip_plus/{mesh_name}'

        shared_steps, _ = get_isomip_plus_mesh_steps(
            resolution, component=component
        )

        for vertical_coordinate in ['z-star']:
            for variant, experiments in _get_variants():
                for experiment in experiments:
                    config = _get_task_config(
                        component,
                        resdir,
                        vertical_coordinate,
                        experiment,
                        variant,
                    )
                    task = IsomipPlusTest(
                        component=component,
                        resdir=resdir,
                        resolution=resolution,
                        experiment=experiment,
                        vertical_coordinate=vertical_coordinate,
                        shared_steps=shared_steps[experiment],
                        config=config,
                        variant=variant,
                    )
                    component.add_task(task)


def _get_variants():
    """
    Get each variant, with None for the default tasks, and its experiments
    """
    return [(None, EXPERIMENTS)] + list(VARIANTS.items())


def _get_task_config(
    component, resdir, vertical_coordinate, experiment, variant
):
    """Get a config parser shared by the steps of one task"""
    taskdir = os.path.join(component.name, resdir, vertical_coordinate)
    if variant is not None:
        taskdir = os.path.join(taskdir, variant)
    filepath = os.path.join(taskdir, experiment, 'isomip_plus.cfg')
    config = PolarisConfigParser(filepath=filepath)
    config.add_from_package('polaris.ocean.eos', 'teos10.cfg')
    config.add_from_package('polaris.ocean.ice_shelf', 'ssh_adjustment.cfg')
    config.add_from_package('polaris.ocean.ice_shelf', 'freeze.cfg')
    config.add_from_package(
        'polaris.tasks.ocean.isomip_plus', 'isomip_plus.cfg'
    )
    if experiment in ['inception', 'wetting', 'drying']:
        config.add_from_package(
            'polaris.tasks.ocean.isomip_plus', 'thin_film.cfg'
        )
    if experiment == 'inception':
        config.add_from_package(
            'polaris.tasks.ocean.isomip_plus', 'inception.cfg'
        )
    if variant is not None:
        config.add_from_package(
            'polaris.tasks.ocean.isomip_plus', f'{variant}.cfg'
        )
    config.set('vertical_grid', 'coord_type', vertical_coordinate)
    return config
