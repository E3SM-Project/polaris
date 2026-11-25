"""
Unit tests for config options that can only be set at setup.
"""

import pickle

import pytest

from polaris import Component, Step


def _step():
    component = Component(name='component')
    step = Step(component=component, name='step', subdir='step')
    step.config.set('section', 'option', 'a')
    step.add_setup_only_option('section', 'option')
    return step


def test_unchanged_setup_only_option_runs():
    step = _step()
    step.record_setup_only_options()

    step.check_setup_only_options()


def test_setup_only_option_changed_after_setup_is_refused():
    """
    Editing the option in the work directory after setup would leave a step
    wired for one value and its config saying another.
    """
    step = _step()
    step.record_setup_only_options()
    step.config.set('section', 'option', 'b')

    with pytest.raises(ValueError, match='polaris setup'):
        step.check_setup_only_options()


def test_setup_only_option_added_after_setup_is_refused():
    step = _step()
    step.config.remove_option('section', 'option')
    step.record_setup_only_options()
    step.config.set('section', 'option', 'b')

    with pytest.raises(ValueError, match='polaris setup'):
        step.check_setup_only_options()


def test_recorded_values_survive_pickling():
    """The values are recorded at setup and checked by a separate process."""
    step = _step()
    step.record_setup_only_options()

    unpickled = pickle.loads(pickle.dumps(step))

    assert unpickled.setup_only_options == {('section', 'option'): 'a'}


def test_step_pickled_before_setup_only_options_has_none():
    step = _step()
    state = step.__getstate__()
    state.pop('setup_only_options')

    unpickled = Step.__new__(Step)
    unpickled.__setstate__(state)

    unpickled.check_setup_only_options()
    assert unpickled.setup_only_options == {}
