from configparser import ConfigParser
from typing import Any, cast

import pytest

from polaris.config import PolarisConfigParser
from polaris.ocean.model import OceanModelStep
from polaris.tasks.ocean import Ocean


class _RecordingStep(OceanModelStep):
    """An OceanModelStep that records the input files setup() adds."""

    def __init__(self, component, name, graph_target):
        # the base classes add input files of their own during __init__
        self.added = []
        super().__init__(
            component=component,
            name=name,
            subdir=name,
            graph_target=graph_target,
        )

    def add_input_file(self, **kwargs: Any):  # type: ignore[override]
        self.added.append(kwargs)

    def _update_ntasks(self):
        # needs a mesh to size resources from, which these tests do not have
        pass

    def _set_gpus_per_task(self):
        pass


def _step(model, graph_target):
    component = Ocean()
    component.model = model
    step = _RecordingStep(
        component=component, name=f'graph_{model}', graph_target=graph_target
    )
    config = ConfigParser()
    config.add_section('ocean')
    config.set('ocean', 'model', model)
    config.add_section('executables')
    config.set('executables', 'component', f'{model}_model')
    config.set('executables', 'partition', 'gpmetis')
    step.config = cast(PolarisConfigParser, config)
    return step


def test_graph_target_is_linked_for_mpas_ocean():
    """
    The usual case: the graph comes from an upstream step's work directory.
    """
    step = _step('mpas-ocean', graph_target='mesh/culled_graph.info')
    step.setup()
    graph_inputs = [
        entry for entry in step.added if entry.get('filename') == 'graph.info'
    ]
    assert len(graph_inputs) == 1
    assert graph_inputs[0]['work_dir_target'] == 'mesh/culled_graph.info'


def test_no_graph_target_adds_nothing():
    """
    A step whose graph comes from somewhere else -- the input-file database,
    say -- adds ``graph.info`` itself before calling ``setup()``.  The base
    class must not also add an entry pointing at nothing, which is what it did
    while ``graph_target=None`` was documented as building the graph but did
    not: the assignment that would have enabled it was overwritten by
    ``ModelStep.__init__``.
    """
    step = _step('mpas-ocean', graph_target=None)
    step.setup()
    assert not [
        entry for entry in step.added if entry.get('filename') == 'graph.info'
    ]


@pytest.mark.parametrize('graph_target', ['mesh/culled_graph.info', None])
def test_omega_never_links_a_graph(graph_target):
    """Omega partitions internally and reads no graph file."""
    step = _step('omega', graph_target=graph_target)
    step.setup()
    assert not [
        entry for entry in step.added if entry.get('filename') == 'graph.info'
    ]
    assert not step.partition_graph
