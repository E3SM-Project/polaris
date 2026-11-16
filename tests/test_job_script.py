import argparse
import inspect
import math
import os
import sys

import pytest

from polaris import Component, Step, Task, provenance
from polaris.__main__ import main as polaris_main
from polaris.config import PolarisConfigParser
from polaris.job import write_job_script
from polaris.setup import (
    _get_concurrent_resources,
    _get_required_resources,
    _run_steps_concurrently,
    add_concurrent_steps_args,
    setup_tasks,
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
    """The option is what setup passes on."""
    assert _run_steps_concurrently(
        get_config('chrysalis', concurrent_steps='True')
    )
    assert not _run_steps_concurrently(
        get_config('chrysalis', concurrent_steps='False')
    )


def test_the_flag_and_the_config_option_are_one_mechanism():
    """
    `--serial` writes the config option rather than travelling beside it,
    so there is one thing that decides this and it is recorded in the config
    a run was set up with.
    """
    config = get_config('chrysalis', concurrent_steps='True')
    assert _run_steps_concurrently(config)

    config.set('job', 'concurrent_steps', 'False', user=True)

    assert not _run_steps_concurrently(config)


def test_serial_and_parallel_flags_set_the_option():
    """
    Neither flag leaves the option to the config; `--serial` and
    `--parallel` set it either way and cannot be given together.
    """
    parser = argparse.ArgumentParser()
    add_concurrent_steps_args(parser)

    assert parser.parse_args([]).concurrent_steps is None
    assert parser.parse_args(['--serial']).concurrent_steps is False
    assert parser.parse_args(['--parallel']).concurrent_steps is True
    assert parser.parse_args(['-P']).concurrent_steps is True
    with pytest.raises(SystemExit):
        parser.parse_args(['--serial', '--parallel'])


def test_setup_and_suite_can_be_asked_without_a_config_file(
    monkeypatch, capsys
):
    """
    Asking for a concurrent run should not require writing a config file.

    It did, and the awkwardness showed up the moment cross-machine
    instructions had to say "a config file containing this option".
    """
    assert 'concurrent_steps' in inspect.signature(setup_tasks).parameters

    # `polaris suite` passes its arguments through to `setup_tasks`, so the
    # only thing left to check is that each front end offers the flag.  This
    # calls the entry point in this process: a fresh interpreter would have to
    # import every task before it could print the help.
    for command in ('setup', 'suite'):
        monkeypatch.setattr(sys, 'argv', ['polaris', command, '--help'])
        with pytest.raises(SystemExit):
            polaris_main()
        helped = capsys.readouterr().out
        for flag in ('--serial', '-P, --parallel'):
            assert flag in helped, f'polaris {command} does not offer {flag}'


def _sized_job(tmp_path, concurrent, machine='chrysalis', **resources):
    """Write a job script sized from resources rather than a node count."""
    config = get_config(machine)
    write_job_script(
        config=config,
        machine=machine,
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


def _node_shape(machine):
    """Cores and GPUs per node, as the machine's config gives them."""
    config = get_config(machine)
    cores = config.getint('parallel', 'cores_per_node')
    gpus = 0
    if config.has_option('parallel', 'gpus_per_node'):
        gpus = config.getint('parallel', 'gpus_per_node')
    return cores, gpus


def test_a_serial_job_is_sized_by_its_widest_step(tmp_path):
    """One step at a time means only the widest step can use the machine."""
    cores_per_node, _ = _node_shape('chrysalis')
    text = _sized_job(
        tmp_path,
        concurrent=False,
        target_cores=800,
        min_cores=36,
        concurrent_cores=10 * cores_per_node,
    )
    assert _nodes_in(text) == math.ceil(math.sqrt(800 * 36) / cores_per_node)


def test_a_concurrent_job_is_sized_for_the_whole_suite(tmp_path):
    """Steps running together are sized by what setup found for them all."""
    cores_per_node, _ = _node_shape('chrysalis')
    text = _sized_job(
        tmp_path,
        concurrent=True,
        target_cores=800,
        min_cores=36,
        concurrent_cores=4.5 * cores_per_node,
    )
    assert _nodes_in(text) == 5


def test_a_gpu_machine_is_sized_by_gpus_or_cores(tmp_path):
    """
    GPUs size the job unless the steps' cores need more nodes, since steps
    that run on CPUs alone need cores whatever the GPUs come to.
    """
    cores_per_node, gpus_per_node = _node_shape('pm-gpu')
    resources = dict(target_cores=24, min_cores=4, target_gpus=24, min_gpus=4)
    by_gpus = _sized_job(
        tmp_path,
        concurrent=True,
        machine='pm-gpu',
        concurrent_gpus=3 * gpus_per_node,
        concurrent_cores=cores_per_node,
        **resources,
    )
    by_cores = _sized_job(
        tmp_path,
        concurrent=True,
        machine='pm-gpu',
        concurrent_gpus=3 * gpus_per_node,
        concurrent_cores=5 * cores_per_node,
        **resources,
    )
    assert _nodes_in(by_gpus) == 3
    assert _nodes_in(by_cores) == 5


def _task_using(component, name, steps):
    task = Task(component=component, name=name, subdir=name)
    for step in steps:
        task.add_step(step)
    return task


def _sized_step(tmp_path, component, name, ntasks, min_tasks, cached=False):
    """A step with resources and no files, as setup would leave it."""
    step = Step(
        component=component,
        name=name,
        subdir=name,
        ntasks=ntasks,
        cpus_per_task=1,
        min_tasks=min_tasks,
        min_cpus_per_task=1,
        cached=cached,
    )
    step.work_dir = str(tmp_path / name)
    os.makedirs(step.work_dir, exist_ok=True)
    step.inputs = []
    step.outputs = []
    return step


def _chain(steps):
    """Make each step depend on the one before it."""
    for before, after in zip(steps[:-1], steps[1:], strict=True):
        after.add_dependency(before, name=before.name)
        # the files add_dependency() declares are setup's to resolve
        after.inputs = []
        before.outputs = []


def test_one_step_is_sized_the_same_either_way(tmp_path):
    """For a single step both extremes are that step's own width."""
    component = Component(name='ocean')
    step = _sized_step(tmp_path, component, 'only', ntasks=800, min_tasks=36)
    tasks = {'task': _task_using(component, 'task', [step])}
    cores, _ = _get_concurrent_resources(tasks)
    serial = math.sqrt(800 * 36)
    assert serial <= cores < serial + 0.01


def test_independent_steps_grow_the_allocation(tmp_path):
    """
    Four steps of width 16 that can all run at once: the geometric mean of
    16, one at a time, and 64, all at once.
    """
    component = Component(name='ocean')
    steps = [
        _sized_step(tmp_path, component, f's{i}', ntasks=64, min_tasks=4)
        for i in range(4)
    ]
    tasks = {'task': _task_using(component, 'task', steps)}
    cores, gpus = _get_concurrent_resources(tasks)
    assert cores == pytest.approx(32)
    assert gpus == 0


def test_steps_that_wait_for_each_other_add_nothing(tmp_path):
    """The same four steps in a chain can only ever run one at a time."""
    component = Component(name='ocean')
    steps = [
        _sized_step(tmp_path, component, f's{i}', ntasks=64, min_tasks=4)
        for i in range(4)
    ]
    _chain(steps)
    tasks = {'task': _task_using(component, 'task', steps)}
    cores, _ = _get_concurrent_resources(tasks)
    assert cores == pytest.approx(16)


def test_a_shared_step_is_counted_once(tmp_path):
    """
    A step shared between tasks runs once, so it is counted once.  It
    appears once per task that runs it, which would make two copies of it
    look as if they could run at the same time.
    """
    component = Component(name='ocean')
    shared = _sized_step(tmp_path, component, 'shared', ntasks=64, min_tasks=4)
    own = _sized_step(tmp_path, component, 'own', ntasks=64, min_tasks=4)
    tasks = {
        'one': _task_using(component, 'one', [shared, own]),
        'two': _task_using(component, 'two', [shared]),
    }
    cores, _ = _get_concurrent_resources(tasks)
    # widths of 16 each: sqrt(16 x 32), not sqrt(16 x 48)
    assert cores == pytest.approx(math.sqrt(16 * 32))
    _, max_of_min_cores, _, _ = _get_required_resources(tasks)
    assert max_of_min_cores == 4


def test_a_cached_step_is_not_sized(tmp_path):
    """A cached step will not run, so it takes no part in the allocation."""
    component = Component(name='ocean')
    cached = _sized_step(
        tmp_path, component, 'cached', ntasks=640, min_tasks=256, cached=True
    )
    run = _sized_step(tmp_path, component, 'run', ntasks=64, min_tasks=4)
    tasks = {'task': _task_using(component, 'task', [cached, run])}
    cores, _ = _get_concurrent_resources(tasks)
    assert cores == pytest.approx(16)
