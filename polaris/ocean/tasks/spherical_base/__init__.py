from typing import Dict

from polaris import Step, Task
from polaris.config import PolarisConfigParser
from polaris.ocean.mesh.spherical import add_spherical_base_mesh_step
from polaris.ocean.tasks.geostrophic.analysis import Analysis
from polaris.ocean.tasks.geostrophic.forward import Forward
from polaris.ocean.tasks.geostrophic.init import Init
from polaris.ocean.tasks.geostrophic.viz import Viz


def add_spherical_base_tasks(component):
    """
    Add tasks that define variants of the geostrophic test

    component : polaris.ocean.Ocean
        the ocean component that the tasks will be added to
    """

    uniform_resolutions = {
        'qu': [30., 60., 90., 120., 150., 180., 240., 270., 300., 360., 480.,
               960., 1920., 3840.],
        'icos': [30., 60., 120., 240., 480., 960., 1920., 3840.],
    }

    nonuniform_resolutions = {
        'rrs': ['6to18km'],
    }

    for prefix, resolution_floats in uniform_resolutions.items():
        for resolution in resolution_floats:
            base_mesh, mesh_name = add_spherical_base_mesh_step(
                component=component, prefix=prefix, resolution=resolution)
            name = f'{prefix}_base_mesh_{mesh_name}'
            subdir = f'spherical/{prefix}/base_mesh/{mesh_name}/task'
            task = Task(component=component, name=name, subdir=subdir)
            task.add_step(base_mesh)
            component.add_task(task)

    for prefix, resolutions_list in nonuniform_resolutions.items():
        for resolutions in resolutions_list:
            base_mesh, mesh_name = add_spherical_base_mesh_step(
                component=component, prefix=prefix, resolutions=resolutions)
            name = f'{prefix}_base_mesh_{mesh_name}'
            subdir = f'spherical/{prefix}/base_mesh/{mesh_name}/task'
            task = Task(component=component, name=name, subdir=subdir)
            task.add_step(base_mesh)
            component.add_task(task)
