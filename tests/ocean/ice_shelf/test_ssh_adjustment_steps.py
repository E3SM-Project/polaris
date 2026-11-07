from polaris.config import PolarisConfigParser
from polaris.ocean.ice_shelf import SshForward, get_ssh_adjustment_steps
from polaris.tasks.ocean import Ocean


def _get_steps(component, config):
    return get_ssh_adjustment_steps(
        component=component,
        sshdir='planar/ice_shelf_test/4km',
        min_resolution=4.0,
        mesh_filename='mesh.nc',
        graph_target='graph.info',
        init_filename='init.nc',
        config=config,
        config_filename='ice_shelf_test.cfg',
        ForwardStep=SshForward,
        package='polaris.ocean.ice_shelf',
    )


def test_ssh_adjustment_steps_in_a_component():
    component = Ocean()
    config = PolarisConfigParser(
        filepath='ocean/planar/ice_shelf_test/4km/ice_shelf_test.cfg'
    )
    config.set('ssh_adjustment', 'iterations', '2')

    steps, final_step = _get_steps(component, config)

    assert list(steps) == [
        'ssh_adjustment/ssh_forward_0',
        'ssh_adjustment/ssh_adjust_0',
        'ssh_adjustment/ssh_forward_1',
        'ssh_adjustment/ssh_adjust_1',
    ]
    assert final_step is steps['ssh_adjustment/ssh_adjust_1']
    for name, step in steps.items():
        assert step.component is component
        assert step.path == f'ocean/planar/ice_shelf_test/4km/{name}'
        assert step.config is config

    # the steps are shared, so a second caller gets the same ones
    steps_again, _ = _get_steps(component, config)
    for name, step in steps.items():
        assert steps_again[name] is step
