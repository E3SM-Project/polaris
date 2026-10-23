"""
Tests for the graph of which steps have to run before which.

These use synthetic steps and a temporary directory, and need no allocation
and no batch system.  What they are checking is that the graph comes from
what steps *declare* -- dependencies and files -- and not from the order
they were listed in, and that a graph which cannot be run is rejected
before anything starts rather than discovered partway through.
"""

import os

import pytest

from polaris import Component, Step
from polaris.run import STEP_COMPLETE_LOG
from polaris.run.graph import build_step_graph


def _make_step(tmp_path, name, inputs=(), outputs=(), cached=False):
    """A step with its files already resolved, as setup would leave them."""
    component = Component(name='ocean')
    step = Step(component=component, name=name, subdir=name, cached=cached)
    step.work_dir = str(tmp_path / name)
    os.makedirs(step.work_dir, exist_ok=True)
    step.inputs = [str(path) for path in inputs]
    step.outputs = [str(path) for path in outputs]
    return step


def _mark_complete(step):
    """Leave the marker a step writes when it finishes successfully."""
    with open(os.path.join(step.work_dir, STEP_COMPLETE_LOG), 'w') as handle:
        handle.write('done')


def _existing(tmp_path, name):
    """A file that is already there, as a downloaded input would be."""
    path = tmp_path / name
    path.write_text('')
    return path


def test_a_declared_dependency_becomes_an_edge(tmp_path):
    """The mechanism for "after that one" when no file names it."""
    first = _make_step(tmp_path, 'first')
    second = _make_step(tmp_path, 'second')
    second.add_dependency(first, name='first')
    # add_dependency() adds files that setup would resolve; the graph is
    # being asked about the declaration rather than about them
    second.inputs = []
    first.outputs = []

    graph = build_step_graph([first, second])

    assert graph.nodes['ocean/second'].requires == frozenset({'ocean/first'})
    assert graph.nodes['ocean/first'].requires == frozenset()


def test_a_produced_file_becomes_an_edge(tmp_path):
    """Neither step names the other; the file is the whole declaration."""
    shared = tmp_path / 'mesh.nc'
    producer = _make_step(tmp_path, 'producer', outputs=[shared])
    consumer = _make_step(tmp_path, 'consumer', inputs=[shared])

    graph = build_step_graph([producer, consumer])

    assert graph.nodes['ocean/consumer'].requires == frozenset(
        {'ocean/producer'}
    )


def test_a_link_to_what_another_step_will_produce_is_an_edge(tmp_path):
    """
    What setup actually leaves behind, and what a real suite exposed.

    Setup links a step's inputs into its own work directory, so a step
    consuming another's output names a link pointing there.  Until the
    other step runs that link dangles: it does not exist, and the file it
    waits for has a different path.  Following the link is what connects
    the two.
    """
    produced = tmp_path / 'producer' / 'init.nc'
    producer = _make_step(tmp_path, 'producer', outputs=[produced])
    consumer = _make_step(tmp_path, 'consumer')
    linked = tmp_path / 'consumer' / 'init.nc'
    os.symlink(produced, linked)
    consumer.inputs = [str(linked)]

    assert not os.path.exists(linked)

    graph = build_step_graph([producer, consumer])

    assert graph.nodes['ocean/consumer'].requires == frozenset(
        {'ocean/producer'}
    )


def test_a_link_to_a_file_nothing_produces_is_still_rejected(tmp_path):
    """Following the link must not turn a real error into an edge."""
    consumer = _make_step(tmp_path, 'consumer')
    linked = tmp_path / 'consumer' / 'init.nc'
    os.symlink(tmp_path / 'nowhere.nc', linked)
    consumer.inputs = [str(linked)]

    with pytest.raises(ValueError, match='does not exist'):
        build_step_graph([consumer])


def test_listed_order_alone_is_not_an_edge(tmp_path):
    """Two steps that declare nothing about each other may run at once."""
    first = _make_step(tmp_path, 'first')
    second = _make_step(tmp_path, 'second')

    graph = build_step_graph([first, second])

    assert graph.nodes['ocean/first'].requires == frozenset()
    assert graph.nodes['ocean/second'].requires == frozenset()


def test_listed_order_is_kept_as_the_tie_break(tmp_path):
    """Two runs of the same work have to make the same choices."""
    steps = [_make_step(tmp_path, name) for name in ('c', 'a', 'b')]

    graph = build_step_graph(steps)

    assert list(graph.nodes) == ['ocean/c', 'ocean/a', 'ocean/b']


def test_a_shared_step_is_one_node(tmp_path):
    """A step in several tasks is listed several times and runs once."""
    shared = _make_step(tmp_path, 'shared')
    other = _make_step(tmp_path, 'other')

    graph = build_step_graph([shared, other, shared])

    assert list(graph.nodes) == ['ocean/shared', 'ocean/other']


def test_a_cycle_is_rejected(tmp_path):
    """Named, because which steps are in it is what makes it fixable."""
    first = _make_step(tmp_path, 'first', outputs=[tmp_path / 'a.nc'])
    second = _make_step(tmp_path, 'second', outputs=[tmp_path / 'b.nc'])
    first.inputs = [str(tmp_path / 'b.nc')]
    second.inputs = [str(tmp_path / 'a.nc')]

    with pytest.raises(ValueError, match='depend on each other'):
        build_step_graph([first, second])


def test_an_input_nothing_produces_is_rejected(tmp_path):
    """Reported at second one rather than at minute forty."""
    step = _make_step(tmp_path, 'step', inputs=[tmp_path / 'missing.nc'])

    with pytest.raises(ValueError, match='does not exist'):
        build_step_graph([step])


def test_an_input_that_already_exists_is_accepted(tmp_path):
    """A downloaded file, or one an earlier run left behind."""
    step = _make_step(tmp_path, 'step', inputs=[_existing(tmp_path, 'in.nc')])

    graph = build_step_graph([step])

    assert graph.nodes['ocean/step'].requires == frozenset()


def test_two_steps_producing_one_file_are_rejected(tmp_path):
    """A race as soon as the two of them can run at the same time."""
    shared = tmp_path / 'out.nc'
    first = _make_step(tmp_path, 'first', outputs=[shared])
    second = _make_step(tmp_path, 'second', outputs=[shared])

    with pytest.raises(ValueError, match='both produce'):
        build_step_graph([first, second])


def test_an_output_linked_to_another_steps_output_is_not_a_collision(
    tmp_path,
):
    """
    What a resumed topography suite exposed.

    A step may finish by making its output a link to another step's output,
    as a smoothing step does when there is no smoothing to do.  On a rerun
    that link is there, and following it made the two steps produce one
    file.  The step that made the link never writes to its target.
    """
    original = tmp_path / 'original' / 'out.nc'
    first = _make_step(tmp_path, 'original', outputs=[original])
    original.write_text('')
    linked = tmp_path / 'linked' / 'out.nc'
    second = _make_step(tmp_path, 'linked', outputs=[linked])
    # relative, as the smoothing step leaves it
    os.symlink(os.path.join('..', 'original', 'out.nc'), linked)
    _mark_complete(first)
    _mark_complete(second)

    graph = build_step_graph([first, second])

    assert graph.nodes['ocean/linked'].requires == frozenset()
    assert graph.nodes['ocean/linked'].satisfied


def test_an_input_waits_for_the_step_whose_output_it_names(tmp_path):
    """
    Not for the step whose output that one links to.

    Following every link to its end would make the consumer of a linked
    output wait for the wrong step, and start before the step it needs has
    rerun.
    """
    original = tmp_path / 'original' / 'out.nc'
    first = _make_step(tmp_path, 'original', outputs=[original])
    original.write_text('')
    linked = tmp_path / 'linked' / 'out.nc'
    second = _make_step(tmp_path, 'linked', outputs=[linked])
    os.symlink(original, linked)
    consumer = _make_step(tmp_path, 'consumer')
    consumer_input = tmp_path / 'consumer' / 'in.nc'
    os.symlink(linked, consumer_input)
    consumer.inputs = [str(consumer_input)]

    graph = build_step_graph([first, second, consumer])

    assert graph.nodes['ocean/consumer'].requires == frozenset(
        {'ocean/linked'}
    )


def test_two_names_for_one_output_through_a_linked_directory_collide(
    tmp_path,
):
    """
    Not following an output's own link must not hide a real race.

    A task links a shared step's directory into its own, so two names for
    one file can differ by a linked directory.  Those are still one file.
    """
    real = tmp_path / 'real'
    real.mkdir()
    alias = tmp_path / 'alias'
    os.symlink(real, alias)
    first = _make_step(tmp_path, 'first', outputs=[real / 'out.nc'])
    second = _make_step(tmp_path, 'second', outputs=[alias / 'out.nc'])

    with pytest.raises(ValueError, match='both produce'):
        build_step_graph([first, second])


def test_an_input_through_a_linked_directory_is_an_edge(tmp_path):
    """The same file named through a task's link to a shared step."""
    real = tmp_path / 'real'
    real.mkdir()
    alias = tmp_path / 'alias'
    os.symlink(real, alias)
    producer = _make_step(tmp_path, 'producer', outputs=[real / 'out.nc'])
    consumer = _make_step(tmp_path, 'consumer', inputs=[alias / 'out.nc'])

    graph = build_step_graph([producer, consumer])

    assert graph.nodes['ocean/consumer'].requires == frozenset(
        {'ocean/producer'}
    )


def test_a_completed_step_is_satisfied_rather_than_run(tmp_path):
    step = _make_step(tmp_path, 'step')
    _mark_complete(step)

    graph = build_step_graph([step])

    assert graph.nodes['ocean/step'].satisfied


def test_a_cached_step_is_satisfied_rather_than_run(tmp_path):
    step = _make_step(tmp_path, 'step', cached=True)

    graph = build_step_graph([step])

    assert graph.nodes['ocean/step'].satisfied


def test_a_step_that_has_not_run_is_not_satisfied(tmp_path):
    step = _make_step(tmp_path, 'step')

    graph = build_step_graph([step])

    assert not graph.nodes['ocean/step'].satisfied


def test_a_satisfied_step_still_carries_its_edges(tmp_path):
    """Its outputs are available to others; it is only not run."""
    shared = tmp_path / 'mesh.nc'
    producer = _make_step(tmp_path, 'producer', outputs=[shared])
    _mark_complete(producer)
    shared.write_text('')
    consumer = _make_step(tmp_path, 'consumer', inputs=[shared])

    graph = build_step_graph([producer, consumer])

    assert graph.nodes['ocean/producer'].satisfied
    assert graph.nodes['ocean/consumer'].requires == frozenset(
        {'ocean/producer'}
    )


def test_a_failure_blocks_everything_behind_it(tmp_path):
    """What the scheduler needs when a step fails: who cannot run now."""
    first = _make_step(tmp_path, 'first', outputs=[tmp_path / 'a.nc'])
    second = _make_step(
        tmp_path,
        'second',
        inputs=[tmp_path / 'a.nc'],
        outputs=[tmp_path / 'b.nc'],
    )
    third = _make_step(tmp_path, 'third', inputs=[tmp_path / 'b.nc'])
    unrelated = _make_step(tmp_path, 'unrelated')

    graph = build_step_graph([first, second, third, unrelated])

    assert graph.dependents('ocean/first') == ('ocean/second',)
    assert graph.descendants('ocean/first') == frozenset(
        {'ocean/second', 'ocean/third'}
    )
    assert graph.descendants('ocean/unrelated') == frozenset()


def test_a_step_may_consume_what_it_produces(tmp_path):
    """A step that rewrites its own output does not wait for itself."""
    shared = tmp_path / 'state.nc'
    step = _make_step(tmp_path, 'step', inputs=[shared], outputs=[shared])

    graph = build_step_graph([step])

    assert graph.nodes['ocean/step'].requires == frozenset()
