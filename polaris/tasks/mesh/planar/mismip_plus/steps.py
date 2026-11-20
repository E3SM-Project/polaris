import os

from polaris.config import PolarisConfigParser
from polaris.resolution import resolution_to_string
from polaris.tasks.mesh import mesh as mesh_component
from polaris.tasks.mesh.planar.mismip_plus.mesh import MismipPlusMesh


def get_mismip_plus_mesh_steps(resolution):
    """
    Get the shared steps for making the MISMIP+ mesh at a given resolution

    Parameters
    ----------
    resolution : float
        The nominal resolution of the mesh in km

    Returns
    -------
    steps : dict of str to polaris.Step
        The steps that make the mesh, keyed by logical step name: ``mesh``

    config : polaris.config.PolarisConfigParser
        The shared config options for the mesh
    """
    subdir = f'planar/mismip_plus/{resolution_to_string(resolution)}'
    config_filename = 'mismip_plus_mesh.cfg'
    filepath = os.path.join(mesh_component.name, subdir, config_filename)

    def create():
        config = PolarisConfigParser(filepath=filepath)
        config.add_from_package(
            'polaris.tasks.mesh.planar.mismip_plus', config_filename
        )
        return config

    config = mesh_component.get_or_create_shared_config(
        filepath=filepath, create=create
    )

    mesh_step = mesh_component.get_or_create_shared_step(
        step_cls=MismipPlusMesh,
        subdir=f'{subdir}/mesh',
        config=config,
        config_filename=config_filename,
        resolution=resolution,
    )
    return {'mesh': mesh_step}, config
