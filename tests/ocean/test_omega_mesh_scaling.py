from polaris.ocean.model import OceanModelStep
from polaris.tasks.ocean import Ocean
from polaris.yaml import PolarisYaml


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


def test_realistic_global_turns_mesh_scaling_on():
    replacements = dict(
        run_duration='0001_00:00:00',
        dt='00:30:00',
        btr_dt='00:01:00',
        time_integrator='split_explicit',
        output_interval='0001_00:00:00',
        output_freq='1',
        output_freq_units='days',
    )
    yaml = PolarisYaml.read(
        filename='forward.yaml',
        package='polaris.tasks.ocean.realistic_global',
        replacements=replacements,
        model='Omega',
        streams_section='IOStreams',
    )
    assert yaml.configs['HorzMesh']['MeshScalingEnable'] is True
