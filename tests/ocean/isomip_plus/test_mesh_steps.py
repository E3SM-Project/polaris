from importlib import import_module

# polaris imports task packages lazily, so import the module itself
isomip_plus = import_module('polaris.tasks.ocean.isomip_plus')


def test_mesh_steps_are_shared():
    steps, config = isomip_plus.get_isomip_plus_mesh_steps(4.0)
    steps_again, config_again = isomip_plus.get_isomip_plus_mesh_steps(4.0)
    assert config_again is config
    assert sorted(steps_again) == sorted(steps)
    for experiment, experiment_steps in steps.items():
        for name, step in experiment_steps.items():
            assert steps_again[experiment][name] is step


def test_mesh_step_paths():
    steps, config = isomip_plus.get_isomip_plus_mesh_steps(2.0)
    resdir = 'ocean/planar/isomip_plus/2km'
    assert config.filepath == f'{resdir}/isomip_plus_topo.cfg'
    assert steps['ocean0']['topo/cull_mesh'].path == f'{resdir}/topo/cull_mesh'
    assert steps['ocean0']['topo_final'] is steps['ocean1']['topo_final']
    assert (
        steps['ocean2']['topo_final'].path
        == f'{resdir}/topo/remap_culled/ocean2'
    )
    assert (
        steps['wetting']['topo_final'].path == f'{resdir}/topo/scale/wetting'
    )
    for experiment_steps in steps.values():
        for step in experiment_steps.values():
            assert step.config is config
