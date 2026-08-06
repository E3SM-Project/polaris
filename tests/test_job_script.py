import os

import pytest

from polaris import provenance
from polaris.config import PolarisConfigParser
from polaris.job import write_job_script


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
