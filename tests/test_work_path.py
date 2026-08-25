import os

import pytest

from polaris import Component, Step


def _step(work_dir):
    component = Component(name='ocean')
    step = Step(component=component, name='test_step')
    step.work_dir = work_dir
    return step


def test_work_path_is_absolute_and_under_work_dir(tmp_path):
    step = _step(str(tmp_path))
    assert step.work_path('output.nc') == os.path.join(
        str(tmp_path), 'output.nc'
    )


def test_work_path_joins_multiple_components(tmp_path):
    step = _step(str(tmp_path))
    assert step.work_path('plots', 'final.png') == os.path.join(
        str(tmp_path), 'plots', 'final.png'
    )


def test_work_path_does_not_depend_on_cwd(tmp_path, monkeypatch):
    """The whole point of the helper: the answer must be the same no matter
    where the process happens to be running from."""
    step = _step(str(tmp_path))
    from_here = step.work_path('output.nc')
    other_dir = tmp_path / 'elsewhere'
    other_dir.mkdir()
    monkeypatch.chdir(other_dir)
    assert step.work_path('output.nc') == from_here


def test_work_path_normalizes_relative_components(tmp_path):
    step = _step(str(tmp_path))
    expected = os.path.join(os.path.dirname(str(tmp_path)), 'sibling.nc')
    assert step.work_path('..', 'sibling.nc') == expected


def test_work_path_raises_before_setup():
    """A step that has not been set up has no work directory, and silently
    returning a path relative to the process working directory would be
    exactly the bug the helper exists to prevent."""
    step = _step('')
    with pytest.raises(ValueError, match='work directory'):
        step.work_path('output.nc')
