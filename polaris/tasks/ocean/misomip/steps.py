import os

from polaris.config import PolarisConfigParser
from polaris.ocean.ice_shelf import get_ssh_adjustment_steps
from polaris.tasks.ocean import ocean
from polaris.tasks.ocean.isomip_plus import get_isomip_plus_mesh_steps
from polaris.tasks.ocean.isomip_plus.ssh_forward import SshForward
from polaris.tasks.ocean.isomip_plus.topo import TopoMap, TopoRemap
from polaris.tasks.ocean.misomip.init import MisomipInit

#: The name of the config file shared by an experiment's ocean steps
CONFIG_FILENAME = 'misomip_ocean.cfg'

#: The name of the config file shared by the topography steps
TOPO_CONFIG_FILENAME = 'isomip_plus_topo.cfg'


def get_misomip_ocean_steps(
    mesh_name,
    resolution,
    experiment,
    ocean_mesh_step,
    land_ice_fields_step,
    ssh_adjustment=True,
):
    """
    Get the shared steps of the ocean component that make the ocean's
    initial condition and forcing for a MISOMIP experiment

    Parameters
    ----------
    mesh_name : str
        The name of the pair of ocean and MALI meshes

    resolution : float
        The resolution of the ocean's mesh in km

    experiment : str
        The experiment

    ocean_mesh_step : polaris.Step
        The step that gave the ocean's mesh latitude and longitude

    land_ice_fields_step : polaris.Step
        The step that computed the land-ice fields on the ocean's mesh

    ssh_adjustment : bool, optional
        Whether the experiment needs an initial condition, made by adjusting
        the SSH to the land-ice pressure, rather than only its forcing

    Returns
    -------
    steps : dict of str to polaris.Step
        The steps, including the ISOMIP+ mesh steps, keyed by their suggested
        symlink names

    config : polaris.config.PolarisConfigParser
        The shared config options for the experiment's ocean steps

    final_step : polaris.Step
        The step that makes the initial condition, or the ``init`` step if
        there is no SSH adjustment
    """
    component = ocean
    pairdir = os.path.join('planar', 'misomip', mesh_name)
    expdir = os.path.join(pairdir, experiment)

    isomip_plus_steps, topo_config = get_isomip_plus_mesh_steps(resolution)
    mesh_steps = isomip_plus_steps['ocean1']
    steps = dict()
    for name in [
        'base_mesh',
        'topo/map_base',
        'topo/remap_base',
        'topo/cull_mesh',
    ]:
        steps[f'isomip_plus/{name}'] = mesh_steps[name]

    # the protocol's bed, remapped without smoothing so that the ocean's
    # grounding line stays where MALI's is
    topo_map = component.get_or_create_shared_step(
        step_cls=TopoMap,
        subdir=os.path.join(pairdir, 'topo', 'map'),
        config=topo_config,
        config_filename=TOPO_CONFIG_FILENAME,
        name='topo_map',
        mesh_name=f'{mesh_name}_ocean',
        mesh_step=mesh_steps['topo/cull_mesh'],
        mesh_filename='culled_mesh.nc',
        method='conserve',
        smooth=False,
    )
    topo_remap = component.get_or_create_shared_step(
        step_cls=TopoRemap,
        subdir=os.path.join(pairdir, 'topo', 'remap'),
        config=topo_config,
        config_filename=TOPO_CONFIG_FILENAME,
        name='topo_remap',
        topo_map=topo_map,
        experiment='ocean1',
    )
    steps['ocean/topo/map'] = topo_map
    steps['ocean/topo/remap'] = topo_remap

    config = _get_config(expdir)
    init = component.get_or_create_shared_step(
        step_cls=MisomipInit,
        subdir=os.path.join(expdir, 'init'),
        config=config,
        config_filename=CONFIG_FILENAME,
        ocean_mesh_step=ocean_mesh_step,
        topo_step=topo_remap,
        land_ice_fields_step=land_ice_fields_step,
        experiment=experiment,
    )
    steps['ocean/init'] = init
    if not ssh_adjustment:
        return steps, config, init

    ssh_steps, final_step = get_ssh_adjustment_steps(
        component=component,
        sshdir=expdir,
        min_resolution=resolution,
        mesh_filename=f'{init.path}/mesh.nc',
        graph_target=f'{init.path}/culled_graph.info',
        init_filename=f'{init.path}/init.nc',
        config=config,
        config_filename=CONFIG_FILENAME,
        ForwardStep=SshForward,
        package='polaris.tasks.ocean.isomip_plus',
        yaml_filename='physics.yaml',
    )
    for name, step in ssh_steps.items():
        steps[f'ocean/{name}'] = step
    return steps, config, final_step


def _get_config(expdir):
    """
    Get or create the shared config for an experiment's ocean steps, those
    of the ISOMIP+ tasks with a thin film, changed for MISOMIP
    """
    filepath = os.path.join(ocean.name, expdir, CONFIG_FILENAME)

    def create():
        config = PolarisConfigParser(filepath=filepath)
        config.add_from_package('polaris.ocean.eos', 'teos10.cfg')
        config.add_from_package(
            'polaris.ocean.ice_shelf', 'ssh_adjustment.cfg'
        )
        config.add_from_package('polaris.ocean.ice_shelf', 'freeze.cfg')
        for filename in ['isomip_plus.cfg', 'thin_film.cfg']:
            config.add_from_package(
                'polaris.tasks.ocean.isomip_plus', filename
            )
        config.add_from_package('polaris.tasks.ocean.misomip', CONFIG_FILENAME)
        config.set('vertical_grid', 'coord_type', 'z-star')
        return config

    return ocean.get_or_create_shared_config(filepath=filepath, create=create)
