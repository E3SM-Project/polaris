import os

import pytest

import polaris.suite
from polaris.config import PolarisConfigParser
from polaris.job import write_job_script
from polaris.setup import _add_suite_config, _get_suite_config
from polaris.suite import setup_suite


def get_basic_config(machine):
    """Build a config for ``machine`` without any suite config options."""
    config = PolarisConfigParser()
    config.add_from_package('polaris', 'default.cfg')
    config.add_from_package('mache.machines', f'{machine}.cfg')
    return config


def get_config(machine, suite_name):
    """Build a config for ``machine`` with ``suite_name``'s options added."""
    config = get_basic_config(machine)
    _add_suite_config(config, 'ocean', suite_name)
    return config


def get_job_script(tmp_path, machine, suite_name, nodes):
    """Write a suite job script and return its text."""
    config = get_config(machine, suite_name)
    write_job_script(
        config=config,
        machine=machine,
        work_dir=str(tmp_path),
        nodes=nodes,
        suite=suite_name,
    )
    script = os.path.join(str(tmp_path), f'job_script.{suite_name}.sh')
    with open(script) as handle:
        return handle.read()


def test_suite_config_overrides_default():
    """A suite's cfg file overrides the polaris default wall time."""
    config = get_config('chrysalis', 'omega_pr')
    assert config.get('job', 'wall_time') == '00:30:00'


def test_suite_without_config_is_not_an_error():
    """A suite with no cfg file leaves the defaults in place."""
    config = get_config('chrysalis', 'cosine_bell')
    assert config.get('job', 'wall_time') == '1:00:00'


@pytest.mark.parametrize('suite_name', ['custom', ''])
def test_no_suite_config_added_without_a_suite(suite_name):
    """Tasks set up outside a suite get no suite config options."""
    config = get_config('chrysalis', suite_name)
    assert config.get('job', 'wall_time') == '1:00:00'


def test_suite_config_reaches_the_job_script(tmp_path):
    """The suite's wall time ends up in the suite's job script."""
    text = get_job_script(tmp_path, 'chrysalis', 'omega_pr', nodes=2)
    assert '#SBATCH --time=00:30:00' in text


def test_the_suites_component_reaches_setup(tmp_path, monkeypatch):
    """
    A suite's config file comes from the component the suite belongs to.  The
    tasks in a suite may belong to other components, so setup cannot work this
    out from the tasks themselves.
    """
    passed = dict()

    def fake_setup_tasks(**kwargs):
        passed.update(kwargs)

    monkeypatch.setattr(polaris.suite, 'setup_tasks', fake_setup_tasks)

    setup_suite(
        component='ocean', suite_name='framework_pr', work_dir=str(tmp_path)
    )

    assert passed['suite_component'] == 'ocean'
    assert passed['suite_name'] == 'framework_pr'


def test_suite_config_stays_out_of_the_basic_config():
    """
    The suite's options go only into the config for the suite's job script.
    The basic config is the source of the config options for every task and
    step in the suite, so the suite must leave it alone.
    """
    basic_config = get_basic_config('chrysalis')
    suite_config = _get_suite_config(basic_config, 'ocean', 'omega_pr')

    assert suite_config.get('job', 'wall_time') == '00:30:00'
    assert basic_config.get('job', 'wall_time') == '1:00:00'


@pytest.mark.parametrize(
    'machine, expected',
    [
        ('chrysalis', '#SBATCH --partition=debug'),
        ('pm-cpu', '#SBATCH --qos=debug'),
        ('frontier', '#SBATCH --qos=debug'),
        ('aurora', '#PBS -q debug'),
    ],
)
def test_pr_suite_reaches_a_debug_target(tmp_path, capsys, machine, expected):
    """
    The PR suite lands on each machine's fast-turnaround target, however
    that machine happens to provide it, and says nothing about the kinds of
    target the machine does not use.
    """
    text = get_job_script(tmp_path, machine, 'omega_pr', nodes=2)
    assert expected in text
    assert 'Warning' not in capsys.readouterr().out


def test_pr_suite_keeps_the_default_frontier_partition(tmp_path):
    """
    Frontier lists ``debug`` under its qos, so the suite's
    ``scheduler_target`` must not disturb the default partition.
    """
    text = get_job_script(tmp_path, 'frontier', 'omega_pr', nodes=2)
    assert '#SBATCH --partition=batch' in text


def test_nightly_suite_uses_a_longer_wall_time(tmp_path):
    """The nightly suite asks for longer than the polaris default."""
    text = get_job_script(tmp_path, 'frontier', 'omega_nightly', nodes=2)
    assert '#SBATCH --time=2:00:00' in text
    assert '#SBATCH --qos=normal' in text
