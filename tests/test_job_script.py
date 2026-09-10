import os

import pytest

from polaris import Component, Step, Task, provenance
from polaris.config import PolarisConfigParser
from polaris.job import write_job_script
from polaris.setup import (
    _get_required_resources,
    _run_steps_concurrently,
)


def get_config(machine=None, **job_options):
    """Build a config for ``machine`` with the given ``[job]`` options set."""
    config = PolarisConfigParser()
    config.add_from_package('polaris', 'default.cfg')
    if machine is not None:
        config.add_from_package('mache.machines', f'{machine}.cfg')
    for option, value in job_options.items():
        config.set('job', option, value)
    return config


def get_job_script(tmp_path, machine, nodes, **job_options):
    """Write a job script for ``machine`` and return its text and options."""
    config = get_config(machine, **job_options)
    options = write_job_script(
        config=config,
        machine=machine,
        work_dir=str(tmp_path),
        nodes=nodes,
    )
    script = os.path.join(str(tmp_path), 'job_script.sh')
    if not os.path.exists(script):
        return None, options
    with open(script) as handle:
        text = handle.read()
    return text, options


def test_qos_request_honored(tmp_path):
    """A QOS the machine supports is passed through to the job script."""
    text, options = get_job_script(
        tmp_path, 'pm-cpu', nodes=2, qos='debug', wall_time='00:20:00'
    )
    assert '#SBATCH --qos=debug' in text
    assert '#SBATCH --time=00:20:00' in text
    assert options.honored
    assert options.reason is None


def test_qos_request_exceeds_wall_clock(tmp_path, capsys):
    """A QOS that cannot fit the requested wall time falls back."""
    text, options = get_job_script(
        tmp_path, 'pm-cpu', nodes=2, qos='debug', wall_time='02:00:00'
    )
    assert '#SBATCH --qos=regular' in text
    assert '#SBATCH --time=02:00:00' in text
    assert not options.honored
    warning = capsys.readouterr().out
    assert 'Warning:' in warning
    assert '00:30:00' in warning
    assert '02:00:00' in warning


def test_qos_request_unavailable(tmp_path, capsys):
    """A QOS the machine does not have falls back with a warning."""
    text, options = get_job_script(
        tmp_path, 'pm-cpu', nodes=2, qos='nonexistent'
    )
    assert '#SBATCH --qos=regular' in text
    assert not options.honored
    warning = capsys.readouterr().out
    assert 'not an available qos' in warning
    assert 'regular, debug, premium' in warning


def test_default_sentinel_is_not_a_request(tmp_path, capsys):
    """The shipped ``<<<default>>>`` values mean "let mache choose"."""
    text, options = get_job_script(tmp_path, 'pm-cpu', nodes=2)
    assert '<<<' not in text
    assert '#SBATCH --qos=regular' in text
    assert '#SBATCH --constraint=cpu' in text
    assert '#SBATCH --job-name=polaris' in text
    assert options.honored
    assert capsys.readouterr().out == ''


def test_partition_request_honored(tmp_path):
    """A partition the machine supports is passed through."""
    text, options = get_job_script(
        tmp_path, 'chrysalis', nodes=2, partition='debug'
    )
    assert '#SBATCH --partition=debug' in text
    assert options.honored


def test_frontier_qos_request_honored(tmp_path):
    """Frontier's debug QOS is honored within its wall-clock limit."""
    text, options = get_job_script(
        tmp_path, 'frontier', nodes=8, qos='debug', wall_time='01:00:00'
    )
    assert '#SBATCH --partition=batch' in text
    assert '#SBATCH --qos=debug' in text
    assert '#SBATCH --time=01:00:00' in text
    assert options.honored


def test_wall_time_capped_by_job_size(tmp_path):
    """A wall time longer than the job-size bin allows is capped."""
    text, options = get_job_script(
        tmp_path, 'frontier', nodes=8, wall_time='04:00:00'
    )
    assert '#SBATCH --time=02:00:00' in text
    assert options.max_wallclock == '02:00:00'
    # capping is not a request that was denied
    assert options.honored


def test_queue_request_honored(tmp_path):
    """A PBS queue the machine supports is passed through."""
    text, options = get_job_script(
        tmp_path, 'aurora', nodes=2, queue='debug', wall_time='00:30:00'
    )
    assert '#PBS -q debug' in text
    assert '#PBS -l walltime=00:30:00' in text
    assert '#PBS -l filesystems=home:flare' in text
    assert options.honored


def test_queue_request_exceeds_wall_clock(tmp_path, capsys):
    """A PBS queue that cannot fit the requested wall time falls back."""
    text, options = get_job_script(
        tmp_path, 'aurora', nodes=2, queue='debug', wall_time='02:00:00'
    )
    assert '#PBS -q capacity' in text
    assert not options.honored
    assert '01:00:00' in capsys.readouterr().out


def test_scheduler_target_maps_to_a_partition(tmp_path, capsys):
    """A target is used as a partition on a machine that lists it there."""
    text, options = get_job_script(
        tmp_path, 'chrysalis', nodes=2, scheduler_target='debug'
    )
    assert '#SBATCH --partition=debug' in text
    assert options.partition == 'debug'
    assert options.honored
    assert capsys.readouterr().out == ''


def test_scheduler_target_maps_to_a_qos(tmp_path, capsys):
    """The same target is used as a QOS on a machine that lists it there."""
    text, options = get_job_script(
        tmp_path,
        'pm-cpu',
        nodes=2,
        scheduler_target='debug',
        wall_time='00:20:00',
    )
    assert '#SBATCH --qos=debug' in text
    assert options.honored
    assert capsys.readouterr().out == ''


def test_scheduler_target_maps_to_a_queue(tmp_path, capsys):
    """The same target is used as a queue on a PBS machine."""
    text, options = get_job_script(
        tmp_path,
        'aurora',
        nodes=2,
        scheduler_target='debug',
        wall_time='00:30:00',
    )
    assert '#PBS -q debug' in text
    assert options.queue == 'debug'
    assert options.honored
    assert capsys.readouterr().out == ''


def test_named_axis_wins_over_scheduler_target(tmp_path):
    """An explicit request wins on the axis it names."""
    text, options = get_job_script(
        tmp_path, 'pm-cpu', nodes=2, scheduler_target='debug', qos='regular'
    )
    assert '#SBATCH --qos=regular' in text
    assert options.honored


def test_scheduler_target_unavailable(tmp_path, capsys):
    """A target on no axis at all falls back with a warning."""
    text, options = get_job_script(
        tmp_path, 'pm-cpu', nodes=2, scheduler_target='nonexistent'
    )
    assert '#SBATCH --qos=regular' in text
    assert not options.honored
    warning = capsys.readouterr().out
    assert 'not an available scheduler target' in warning
    assert 'qos: regular, debug, premium' in warning


def test_constraint_request_honored(tmp_path, capsys):
    """A constraint the machine supports is passed through."""
    text, options = get_job_script(
        tmp_path, 'pm-gpu', nodes=2, constraint='gpu'
    )
    assert '#SBATCH --constraint=gpu' in text
    assert options.honored
    assert capsys.readouterr().out == ''


def test_constraint_request_unavailable(tmp_path, capsys):
    """A constraint the machine does not have falls back with a warning."""
    text, options = get_job_script(
        tmp_path, 'pm-gpu', nodes=2, constraint='cpu'
    )
    assert '#SBATCH --constraint=gpu' in text
    assert not options.honored
    warning = capsys.readouterr().out
    assert 'not an available constraint' in warning
    assert 'available: gpu' in warning


def test_constraint_request_on_machine_without_constraints(tmp_path, capsys):
    """A constraint request on a machine that defines none is ignored."""
    text, options = get_job_script(
        tmp_path, 'chrysalis', nodes=2, constraint='anything'
    )
    assert '--constraint' not in text
    assert options.constraint == ''
    # the machine has no notion of a constraint, so there was no choice to
    # deny
    assert options.honored
    assert capsys.readouterr().out == ''


def test_request_on_an_axis_the_machine_does_not_use(tmp_path, capsys):
    """A QOS request on a machine that defines no QOS is ignored."""
    text, options = get_job_script(
        tmp_path, 'chrysalis', nodes=2, partition='debug', qos='debug'
    )
    assert '#SBATCH --partition=debug' in text
    assert '--qos' not in text
    assert options.honored
    assert capsys.readouterr().out == ''


def test_single_node_writes_no_script(tmp_path):
    """No job script is written for machines without a job scheduler."""
    config = get_config()
    config.set('parallel', 'system', 'single_node')
    options = write_job_script(
        config=config,
        machine=None,
        work_dir=str(tmp_path),
        nodes=1,
    )
    assert options is None
    assert not os.path.exists(os.path.join(str(tmp_path), 'job_script.sh'))


def test_provenance_agrees_with_job_script(tmp_path):
    """Provenance records the options the job script actually used."""
    text, options = get_job_script(
        tmp_path, 'pm-cpu', nodes=2, qos='debug', wall_time='02:00:00'
    )
    # the request was not honored, so provenance must not report it
    assert '#SBATCH --qos=regular' in text
    provenance.write(str(tmp_path), tasks={}, job_options=options)
    with open(os.path.join(str(tmp_path), 'provenance')) as handle:
        recorded = handle.read()
    assert 'qos: regular' in recorded
    assert 'constraint: cpu' in recorded
    # pm-cpu has no partitions and is not a PBS machine
    assert 'partition:' not in recorded
    assert 'queue:' not in recorded


def test_provenance_without_a_job_script(tmp_path):
    """No scheduler metadata is recorded when no job script was written."""
    provenance.write(str(tmp_path), tasks={}, job_options=None)
    with open(os.path.join(str(tmp_path), 'provenance')) as handle:
        recorded = handle.read()
    for label in ('partition:', 'qos:', 'queue:', 'constraint:'):
        assert label not in recorded


@pytest.mark.parametrize(
    'option', ['partition', 'qos', 'constraint', 'scheduler_target']
)
def test_empty_option_is_not_a_request(tmp_path, option):
    """An empty ``[job]`` option is treated as no request at all."""
    text, options = get_job_script(tmp_path, 'pm-cpu', nodes=2, **{option: ''})
    assert '<<<' not in text
    assert options.honored


def test_a_job_script_runs_the_serial_path_by_default(tmp_path):
    """What every suite has been validated against."""
    config = get_config('chrysalis')
    write_job_script(
        config=config,
        machine='chrysalis',
        work_dir=str(tmp_path),
        nodes=2,
        suite='omega_pr',
    )
    with open(os.path.join(str(tmp_path), 'job_script.omega_pr.sh')) as handle:
        text = handle.read()

    assert 'polaris serial omega_pr' in text
    assert 'polaris parallel' not in text


def test_a_job_script_runs_the_concurrent_path_when_asked(tmp_path):
    """The opt-in, which is a config option so that setup stays the same."""
    config = get_config('chrysalis')
    write_job_script(
        config=config,
        machine='chrysalis',
        work_dir=str(tmp_path),
        nodes=2,
        suite='omega_pr',
        concurrent=True,
    )
    with open(os.path.join(str(tmp_path), 'job_script.omega_pr.sh')) as handle:
        text = handle.read()

    assert 'polaris parallel omega_pr' in text
    assert 'polaris serial' not in text


def test_asking_for_the_concurrent_path_is_reading_the_option(tmp_path):
    """The option is what setup passes on, and it is off unless it is set."""
    assert not _run_steps_concurrently(get_config('chrysalis'))
    assert _run_steps_concurrently(
        get_config('chrysalis', concurrent_steps='True')
    )
    assert not _run_steps_concurrently(
        get_config('chrysalis', concurrent_steps='False')
    )


def test_the_flag_and_the_config_option_are_one_mechanism():
    """
    `--concurrent_steps` writes the config option rather than travelling
    beside it, so there is one thing that decides this and it is recorded in
    the config a run was set up with.
    """
    config = get_config('chrysalis')
    assert not _run_steps_concurrently(config)

    config.set('job', 'concurrent_steps', 'True', user=True)

    assert _run_steps_concurrently(config)


def test_setup_and_suite_can_be_asked_without_a_config_file():
    """
    Asking for a concurrent run should not require writing a config file.

    It did, and the awkwardness showed up the moment cross-machine
    instructions had to say "a config file containing this option".
    """
    import inspect
    import subprocess
    import sys

    from polaris.setup import setup_tasks

    assert 'concurrent_steps' in inspect.signature(setup_tasks).parameters

    # `polaris suite` passes its arguments through to `setup_tasks`, so the
    # only thing left to check is that each front end offers the flag
    for command in ('setup', 'suite'):
        helped = subprocess.run(
            [sys.executable, '-m', 'polaris', command, '--help'],
            capture_output=True,
            text=True,
        )
        assert '--concurrent_steps' in helped.stdout, (
            f'polaris {command} does not offer the flag'
        )


def _sized_job(tmp_path, concurrent, **resources):
    """Write a job script sized from resources rather than a node count."""
    config = get_config('chrysalis')
    write_job_script(
        config=config,
        machine='chrysalis',
        work_dir=str(tmp_path),
        concurrent=concurrent,
        **resources,
    )
    with open(os.path.join(str(tmp_path), 'job_script.sh')) as handle:
        return handle.read()


def _nodes_in(text):
    for line in text.splitlines():
        if line.startswith('#SBATCH --nodes='):
            return int(line.split('=')[1])
    raise AssertionError(f'no node count in:\n{text}')


def test_a_serial_job_is_sized_by_its_widest_step(tmp_path):
    """One step at a time means only the widest step can use the machine."""
    # sqrt(800 * 36) = 169.7 cores, which is 3 of Chrysalis' 64-core nodes
    text = _sized_job(
        tmp_path,
        concurrent=False,
        target_cores=800,
        min_cores=36,
        sum_min_cores=310,
    )
    assert _nodes_in(text) == 3


def test_a_concurrent_job_holds_every_step_at_once(tmp_path):
    """Steps running together can use more than the widest of them."""
    # the same suite, whose steps need 310 cores between them at their
    # smallest: 5 nodes rather than 3
    text = _sized_job(
        tmp_path,
        concurrent=True,
        target_cores=800,
        min_cores=36,
        sum_min_cores=310,
    )
    assert _nodes_in(text) == 5


def test_a_concurrent_job_grows_as_a_suite_gains_steps(tmp_path):
    """The point of the sum: more tests ask for more of the machine."""
    smaller = _sized_job(
        tmp_path,
        concurrent=True,
        target_cores=800,
        min_cores=36,
        sum_min_cores=310,
    )
    larger = _sized_job(
        tmp_path,
        concurrent=True,
        target_cores=800,
        min_cores=36,
        sum_min_cores=620,
    )
    assert _nodes_in(larger) == 2 * _nodes_in(smaller)


def test_one_step_is_sized_the_same_either_way(tmp_path):
    """
    With one step the sum is that step's own minimum, which the geometric
    mean already exceeds, so concurrency cannot change the answer.
    """
    resources = dict(target_cores=800, min_cores=36, sum_min_cores=36)
    serial = _sized_job(tmp_path, concurrent=False, **resources)
    concurrent = _sized_job(tmp_path, concurrent=True, **resources)
    assert _nodes_in(serial) == _nodes_in(concurrent) == 3


def test_a_concurrent_job_never_asks_for_less_than_the_widest_step(tmp_path):
    """A suite of tiny steps is still sized to run its one big one."""
    text = _sized_job(
        tmp_path,
        concurrent=True,
        target_cores=800,
        min_cores=36,
        sum_min_cores=40,
    )
    assert _nodes_in(text) == 3


def _task_using(component, name, steps):
    task = Task(component=component, name=name, subdir=name)
    for step in steps:
        task.add_step(step)
    return task


def test_a_shared_step_is_counted_once(tmp_path):
    """
    A step shared between tasks runs once, so the sum of the minima has to
    count it once.  It appears once per task that runs it, which makes no
    difference to a maximum and inflates a sum.
    """
    component = Component(name='ocean')
    shared = Step(
        component=component,
        name='shared',
        subdir='shared',
        ntasks=8,
        cpus_per_task=1,
        min_tasks=4,
        min_cpus_per_task=1,
    )
    own = Step(
        component=component,
        name='own',
        subdir='own',
        ntasks=2,
        cpus_per_task=1,
        min_tasks=1,
        min_cpus_per_task=1,
    )
    tasks = {
        'one': _task_using(component, 'one', [shared, own]),
        'two': _task_using(component, 'two', [shared]),
    }
    _, max_of_min_cores, _, _, sum_of_min_cores, _ = _get_required_resources(
        tasks
    )
    # 4 for the shared step and 1 for the other, not 4 + 1 + 4
    assert sum_of_min_cores == 5
    assert max_of_min_cores == 4
