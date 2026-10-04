from polaris.ocean.model import OceanModelStep
from polaris.tasks.ocean import Ocean


def test_mesh_scaling_is_off_unless_a_task_turns_it_on():
    """
    Omega scales horizontal mixing with cell width by default, but most tasks
    are defined with constant coefficients, so every ocean model step turns
    it off first.  It is added in the constructor, so that the yaml files a
    task adds at setup come later and win.
    """
    step = OceanModelStep(component=Ocean(), name='forward', ntasks=1)
    assert step.model_config_data[0] == {
        'options': {'MeshScalingEnable': False},
        'config_model': 'Omega',
    }
