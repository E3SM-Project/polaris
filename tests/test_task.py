from polaris import Component, Step, Task


def _component():
    return Component(name='ocean')


def _task(component, subdir):
    return Task(component=component, name=subdir.split('/')[-1], subdir=subdir)


def _step(component, subdir):
    return Step(component=component, name=subdir.split('/')[-1], subdir=subdir)


def test_add_step_keeps_a_symlink_to_a_step_elsewhere():
    """
    The ordinary case: a task gathers shared steps that live higher up the
    tree, and the symlinks are the only thing that puts them in one place.
    """
    component = _component()
    task = _task(component, 'mesh/task')
    step = _step(component, 'shared/init')
    task.add_step(step, symlink='init')

    assert task.step_symlinks == {'init': 'init'}


def test_add_step_drops_a_symlink_beside_the_step():
    """
    A ``get_*_steps()`` helper suggests one symlink name per step, which suits
    a consumer whose task is elsewhere.  A task that lives in the steps' own
    directory can pass those through, and the symlink would land next to what
    it points to -- ``cull_mask`` beside ``mask`` -- which only adds a second
    name for something already in view.
    """
    component = _component()
    task = _task(component, 'icos480km/topo/cull')
    step = _step(component, 'icos480km/topo/cull/mask')
    task.add_step(step, symlink='cull_mask')

    assert task.step_symlinks == {}
    # the step itself is added as usual
    assert task.steps['mask'] is step
    assert 'mask' in task.steps_to_run


def test_add_step_keeps_a_symlink_to_a_step_nested_deeper():
    """
    Surfacing a step from further down under a descriptive name is what
    symlinks are for, so only the side-by-side case is dropped.
    """
    component = _component()
    task = _task(component, 'icos480km/topo/remap')
    step = _step(component, 'icos480km/topo/remap/unsmoothed/viz')
    task.add_step(step, symlink='viz_remapped_unsmoothed_topo')

    assert task.step_symlinks == {'viz': 'viz_remapped_unsmoothed_topo'}


def test_add_step_compares_across_components():
    """
    Two components can have the same subdirectory layout, so a step from
    another component that happens to share the task's subdirectory is still
    somewhere else on disk and still needs its symlink.
    """
    task = _task(_component(), 'topo/cull')
    step = _step(Component(name='mesh'), 'topo/cull/mask')
    task.add_step(step, symlink='cull_mask')

    assert task.step_symlinks == {'mask': 'cull_mask'}


def test_add_step_drops_a_symlink_naming_the_step_itself():
    # the degenerate case of the same thing: the link would point to itself
    component = _component()
    task = _task(component, 'topo/cull')
    step = _step(component, 'topo/cull/mask')
    task.add_step(step, symlink='mask')

    assert task.step_symlinks == {}
