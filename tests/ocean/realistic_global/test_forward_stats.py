import pytest

from polaris.ocean.model import OceanModelStep
from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.realistic_global import add_realistic_global_tasks

CACHED_FORWARD = 'spherical/realistic_global/e3sm-qu240/cached_forward'
ANALYSIS_OUTPUT = 'spherical/realistic_global/e3sm-qu240/analysis_output'
RESTART = 'spherical/realistic_global/e3sm-qu240/restart'

STATS_FILENAMES = {
    'mpas-ocean': 'global_stats.nc',
    'omega': 'global_stats_1DayInstants',
}


@pytest.mark.parametrize(
    'task_subdir, forward_name, model',
    [
        (f'{CACHED_FORWARD}/split_explicit', 'short', 'mpas-ocean'),
        (f'{CACHED_FORWARD}/split_explicit', 'short', 'omega'),
        (f'{ANALYSIS_OUTPUT}/1_year', 'forward', 'omega'),
    ],
)
def test_forward_declares_the_stats_file_global_stats_reads(
    monkeypatch, task_subdir, forward_name, model
):
    """
    The forward step declares the statistics file that ``global_stats``
    links, so that ``polaris parallel`` can find a step that produces it when
    the two run together.
    """
    # the model step's own setup needs a machine and a model build, neither
    # of which is what this test is about
    monkeypatch.setattr(OceanModelStep, 'setup', lambda self: None)
    task = _task(task_subdir, model)
    forward = task.steps[forward_name]
    stats = task.steps['global_stats']

    forward.setup()
    stats.setup()

    stats_filename = STATS_FILENAMES[model]
    assert forward.get_stats_filename() == stats_filename
    assert stats_filename in forward.outputs
    targets = [entry['work_dir_target'] for entry in stats.input_data]
    assert targets == [f'{forward.path}/{stats_filename}']


def test_a_run_shorter_than_its_stats_interval_declares_no_stats_file(
    monkeypatch,
):
    """
    The restart task's runs are hours long, shorter than the one-day
    statistics interval, and Omega writes no statistics for them.
    """
    monkeypatch.setattr(OceanModelStep, 'setup', lambda self: None)
    task = _task(RESTART, 'omega')
    for name in ['full_run', 'restart_run']:
        step = task.steps[name]
        assert step.get_stats_filename() is None
        step.setup()
        assert not any('global_stats' in output for output in step.outputs)


def _task(task_subdir, model):
    """A registered task, with its config combined for ``model``"""
    component = Ocean()
    add_realistic_global_tasks(component=component)
    task = component.tasks[task_subdir]
    config = task.config
    config.add_from_package('polaris.ocean', 'ocean.cfg')
    config.set('ocean', 'model', model)
    config.combine()
    return task
