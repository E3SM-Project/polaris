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


def get_shipped_option(package, filename, option):
    """Read a ``[job]`` option from a config file that ships with Polaris."""
    config = PolarisConfigParser()
    config.add_from_package(package, filename)
    return config.get('job', option)


def suite_option(suite_name, option):
    """Read a ``[job]`` option from an ocean suite's config file."""
    return get_shipped_option(
        'polaris.suites.ocean', f'{suite_name}.cfg', option
    )


def default_wall_time():
    """The wall time in the polaris defaults."""
    return get_shipped_option('polaris', 'default.cfg', 'wall_time')


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
    assert config.get('job', 'wall_time') == suite_option(
        'omega_pr', 'wall_time'
    )


def test_suite_without_config_is_not_an_error():
    """A suite with no cfg file leaves the defaults in place."""
    config = get_config('chrysalis', 'cosine_bell')
    assert config.get('job', 'wall_time') == default_wall_time()


@pytest.mark.parametrize('suite_name', ['custom', ''])
def test_no_suite_config_added_without_a_suite(suite_name):
    """Tasks set up outside a suite get no suite config options."""
    config = get_config('chrysalis', suite_name)
    assert config.get('job', 'wall_time') == default_wall_time()


def test_suite_config_reaches_the_job_script(tmp_path):
    """The suite's wall time ends up in the suite's job script."""
    text = get_job_script(tmp_path, 'chrysalis', 'omega_pr', nodes=2)
    wall_time = suite_option('omega_pr', 'wall_time')
    assert f'#SBATCH --time={wall_time}' in text


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

    assert suite_config.get('job', 'wall_time') == suite_option(
        'omega_pr', 'wall_time'
    )
    assert basic_config.get('job', 'wall_time') == default_wall_time()


@pytest.mark.parametrize(
    'machine, directive',
    [
        ('chrysalis', '#SBATCH --partition='),
        ('pm-cpu', '#SBATCH --qos='),
        ('frontier', '#SBATCH --qos='),
        ('aurora', '#PBS -q '),
    ],
)
def test_pr_suite_reaches_its_scheduler_target(
    tmp_path, capsys, machine, directive
):
    """
    The PR suite lands on its scheduler target on each machine, however that
    machine happens to provide it, and says nothing about the kinds of
    target the machine does not use.
    """
    target = suite_option('omega_pr', 'scheduler_target')
    text = get_job_script(tmp_path, machine, 'omega_pr', nodes=2)
    assert f'{directive}{target}' in text
    assert 'Warning' not in capsys.readouterr().out


def test_pr_suite_keeps_the_default_frontier_partition(tmp_path):
    """
    Frontier lists ``debug`` under its qos, so the suite's
    ``scheduler_target`` must not disturb the default partition.
    """
    text = get_job_script(tmp_path, 'frontier', 'omega_pr', nodes=2)
    assert '#SBATCH --partition=batch' in text


def test_nightly_suite_wall_time_reaches_the_job_script(tmp_path):
    """The nightly suite's wall time, not the default, is in its script."""
    wall_time = suite_option('omega_nightly', 'wall_time')
    text = get_job_script(tmp_path, 'frontier', 'omega_nightly', nodes=2)
    assert f'#SBATCH --time={wall_time}' in text
    assert '#SBATCH --qos=normal' in text
