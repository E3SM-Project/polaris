from types import SimpleNamespace

import polaris.tasks.e3sm.init.topo.remap.viz as remap_viz
from polaris.tasks.e3sm.init import e3sm_init
from polaris.tasks.e3sm.init.topo.remap import get_remap_topo_steps
from polaris.tasks.mesh import mesh as mesh_component

MESH_NAME = 'u-oi240-lr240'


def test_viz_step_depends_on_its_remap_step():
    steps = _get_steps()

    for suffix in ['unsmoothed', 'smoothed']:
        remap_step = steps[f'remap_{suffix}_topo']
        viz_step = steps[f'viz_remapped_{suffix}_topo']
        assert viz_step.dependencies['remap'] is remap_step
        assert remap_step.is_dependency
        assert 'step_after_run.pickle' in remap_step.outputs


def test_viz_step_skips_when_remapping_was_skipped(monkeypatch):
    steps = _get_steps()
    viz_step = steps['viz_remapped_smoothed_topo']

    # at run time, the dependency is the remap step unpickled after it ran,
    # not the setup-time remap_step attribute
    viz_step.remap_step.do_remapping = True
    viz_step.dependencies['remap'] = SimpleNamespace(
        do_remapping=False, smoothing=True
    )

    def _fail_open_dataset(filename):
        raise AssertionError(f'{filename} should not be opened')

    monkeypatch.setattr(remap_viz, 'open_dataset', _fail_open_dataset)

    viz_step.run()


def _get_steps():
    for component in [e3sm_init, mesh_component]:
        component.tasks.clear()
        component.steps.clear()
        component.configs.clear()

    steps, _ = get_remap_topo_steps(
        mesh_name=MESH_NAME,
        smoothing=True,
        include_viz=True,
    )
    return steps
