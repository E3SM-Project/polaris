"""
Render a placement against every machine Polaris supports.

mache has its own version of this over the configs *it* ships.  This one
exists because Polaris assembles the config that mache is given -- its own
machine files are layered over mache's -- so a Polaris config file can break
placement on a machine without mache noticing.  Rendering here is what
catches that, rather than a machine finding out at run time.

No allocation is needed: the batch environment is faked, and both eras of
Slurm are rendered because the flags differ completely across the 20.11
change and CI will only ever have one of them.
"""

import importlib.resources as imp_res
from unittest import mock

import pytest
from mache.parallel import PlacementSupport, ResourcePlacement
from mache.parallel.pbs import PbsSystem
from mache.parallel.single_node import SingleNodeSystem
from mache.parallel.slurm import SlurmSystem

from polaris.config import PolarisConfigParser

# both eras of Slurm, since a site can be either and CI is neither
MODERN_SLURM = (25, 11)
LEGACY_SLURM = (20, 2)

NODES = ('node0001', 'node0002')


def _fixed(value):
    """Make a callable returning a value, bound now rather than at call."""
    return lambda: value


def _machines():
    """Every machine Polaris ships a config for."""
    names = []
    for entry in imp_res.files('polaris.machines').iterdir():
        name = entry.name
        if name.endswith('.cfg') and not name.startswith('default'):
            names.append(name[: -len('.cfg')])
    return sorted(names)


def _compilers(config):
    """
    Every compiler a machine can actually be deployed with.

    Taken from the ``mpi_<compiler>`` options in ``[deploy]``, which are what
    define the valid combinations, plus any compiler that has parallel
    options of its own.  The two are not the same set, and the difference is
    where the interesting cases live: a compiler with no
    ``[parallel.<compiler>]`` section falls back to the base ``[parallel]``,
    and on pm-gpu that fallback is the deployment that has the GPUs.
    """
    compilers = set()
    if config.has_section('deploy'):
        for option in config.options('deploy'):
            if option.startswith('mpi_'):
                compilers.add(option[len('mpi_') :])
    for section in config.sections():
        if section.startswith('parallel.'):
            compilers.add(section[len('parallel.') :])
    if len(compilers) == 0:
        compilers.add('')
    return sorted(compilers)


def _config(machine, compiler=''):
    """Assemble the config a Polaris run would see for a machine."""
    config = PolarisConfigParser()
    config.add_from_package('polaris', 'default.cfg')
    config.add_from_package(
        'mache.machines', f'{machine}.cfg', exception=False
    )
    config.add_from_package('polaris.machines', f'{machine}.cfg')
    config.set('build', 'machine', machine, user=True)
    config.set('build', 'compiler', compiler, user=True)
    config.combine()
    return config.combined


def _systems(machine, compiler):
    """
    Yield ``(label, system)`` from inside a faked batch environment.

    Each is yielded from inside the context that fakes it and stays there
    until the caller asks for the next one, because ``placement_support`` is
    read every time it is asked, not stored.
    """
    config = _config(machine, compiler)
    system_name = config.get('parallel', 'system', fallback=None)

    if system_name == 'slurm':
        for label, version in (
            ('modern', MODERN_SLURM),
            ('legacy', LEGACY_SLURM),
        ):
            with mock.patch.dict('os.environ', {'SLURM_JOB_ID': '12345'}):
                with mock.patch(
                    'mache.parallel.slurm._get_subprocess_int',
                    lambda args: len(NODES),
                ):
                    with mock.patch(
                        'mache.parallel.slurm.get_slurm_version',
                        _fixed(version),
                    ):
                        yield label, SlurmSystem(config)
    elif system_name == 'pbs':
        with mock.patch.dict('os.environ', {'PBS_JOBID': '1.server'}):
            with mock.patch.object(
                PbsSystem,
                '_get_node_count_from_qstat',
                lambda self: len(NODES),
            ):
                # the launcher is probed by running it, and it is not
                # installed wherever the tests happen to run
                with mock.patch(
                    'mache.parallel.pbs.is_pals_launcher', lambda exe: True
                ):
                    yield '', PbsSystem(config)
    elif system_name == 'single_node':
        yield '', SingleNodeSystem(config)


def _cases():
    """Every machine, compiler and Slurm era worth rendering."""
    cases = []
    for machine in _machines():
        for compiler in _compilers(_config(machine)):
            cases.append((machine, compiler))
    return cases


@pytest.mark.parametrize('machine,compiler', _cases())
def test_no_placement_renders_the_command_polaris_already_built(
    machine, compiler
):
    """A step that does not ask to be confined must not be confined."""
    for _, system in _systems(machine, compiler):
        command = system.get_parallel_command(
            args=['model'], ntasks=2, cpus_per_task=4
        )
        rendered = ' '.join(command)
        assert '--exact' not in rendered
        assert '--gres=none' not in rendered
        assert 'mask_cpu' not in rendered
        assert '--hosts' not in rendered
        assert ' -w ' not in f' {rendered} '


@pytest.mark.parametrize('machine,compiler', _cases())
def test_a_placement_on_one_node_confines_the_launch(machine, compiler):
    for label, system in _systems(machine, compiler):
        if system.placement_support is PlacementSupport.NONE:
            continue
        command = system.get_parallel_command(
            args=['model'],
            ntasks=2,
            cpus_per_task=4,
            placement=_placement(nodes=NODES[:1]),
        )
        _assert_confined(system, command, nodes=NODES[:1], label=label)


@pytest.mark.parametrize('machine,compiler', _cases())
def test_a_placement_can_span_several_nodes(machine, compiler):
    for label, system in _systems(machine, compiler):
        if system.placement_support is PlacementSupport.NONE:
            continue
        placement = _placement(nodes=NODES)
        if isinstance(system, SingleNodeSystem):
            # a machine with one node cannot honor a placement naming two,
            # and says so rather than running on whichever it feels like
            with pytest.raises(ValueError, match='has only one'):
                system.get_parallel_command(
                    args=['model'],
                    ntasks=2,
                    cpus_per_task=4,
                    placement=placement,
                )
            continue
        command = system.get_parallel_command(
            args=['model'],
            ntasks=2,
            cpus_per_task=4,
            placement=placement,
        )
        _assert_confined(system, command, nodes=NODES, label=label)


@pytest.mark.parametrize('machine,compiler', _cases())
def test_needing_no_gpus_says_so_explicitly(machine, compiler):
    """
    Silence about GPUs is read as a claim on every one on the node, which is
    what stopped concurrent steps on the GPU machines.
    """
    for label, system in _systems(machine, compiler):
        if system.placement_support is PlacementSupport.NONE:
            continue
        command = system.get_parallel_command(
            args=['model'],
            ntasks=2,
            cpus_per_task=4,
            placement=_placement(nodes=NODES[:1], gpus=0),
        )
        rendered = ' '.join(command)
        if isinstance(system, SlurmSystem) and label == 'modern':
            assert '--gres=none' in rendered
        elif isinstance(system, PbsSystem):
            variable = system.get_config('gpu_visible_devices_var')
            if variable:
                # asserted against the argument list rather than the joined
                # string: mache moved from `--env=VAR=` to `--env VAR=`
                # because PALS rejected the first form, and a substring
                # match on the old spelling would have gone on passing for a
                # command Aurora could not run
                assert f'{variable}=' in command
                assert '--env' in command


@pytest.mark.parametrize('machine,compiler', _cases())
def test_needing_gpus_asks_for_a_total(machine, compiler):
    """
    A per-task count was measured not to confine a launch on either GPU
    machine, while a total does.
    """
    for _, system in _systems(machine, compiler):
        if system.placement_support is PlacementSupport.NONE:
            continue
        gpus_per_node = system.gpus_per_node or 0
        if gpus_per_node < 2:
            continue
        placement = _placement(nodes=NODES[:1], gpus=2, system=system)
        if (
            isinstance(system, SlurmSystem)
            and system.placement_support is PlacementSupport.CPU_BINDING
        ):
            # a pre-20.11 Slurm has no way to give a step a share of the
            # node's GPUs, and says so rather than rendering something that
            # would not confine anything
            with pytest.raises(ValueError, match='Placing GPUs needs Slurm'):
                system.get_parallel_command(
                    args=['model'],
                    ntasks=2,
                    cpus_per_task=4,
                    placement=placement,
                )
            continue
        command = system.get_parallel_command(
            args=['model'], ntasks=2, cpus_per_task=4, placement=placement
        )
        rendered = ' '.join(command)
        assert '--gpus-per-task' not in rendered
        if isinstance(system, SlurmSystem):
            assert '--gpus=2' in rendered


def _placement(nodes, gpus=0, system=None):
    """Build a placement big enough for 2 tasks of 4 cores."""
    gpu_ids = None
    if gpus > 0 and system is not None:
        variable = system.get_config('gpu_visible_devices_var')
        if variable is not None and variable.strip() != '':
            gpu_ids = tuple(range(gpus))
    return ResourcePlacement(
        nodes=nodes, cores=tuple(range(8)), gpus=gpus, gpu_ids=gpu_ids
    )


def _assert_confined(system, command, nodes, label):
    """Check that a rendered command names the placement it was given."""
    rendered = ' '.join(command)
    if isinstance(system, SlurmSystem):
        assert f'-w {",".join(nodes)}' in rendered
        if label == 'modern':
            assert '--exact' in rendered
        else:
            assert 'mask_cpu' in rendered
    elif isinstance(system, PbsSystem):
        assert f'--hosts {",".join(nodes)}' in rendered
        assert '--cpu-bind list:' in rendered
    elif isinstance(system, SingleNodeSystem):
        assert command[0] == 'taskset'


def test_some_machine_actually_exercises_the_gpu_case():
    """
    Guard against the GPU checks above quietly skipping everywhere.

    Each of them bails out on a config that reports no GPUs, which is the
    right thing to do per config and the wrong thing to discover about the
    whole suite.
    """
    with_gpus = []
    for machine, compiler in _cases():
        for _, system in _systems(machine, compiler):
            if (system.gpus_per_node or 0) >= 2:
                with_gpus.append(f'{machine}/{compiler}')
                break
    assert len(with_gpus) > 0, 'no machine config reports any GPUs'
    machines = {entry.split('/')[0] for entry in with_gpus}
    assert {'pm-gpu', 'frontier', 'aurora'} <= machines


@pytest.mark.parametrize('machine,compiler', _cases())
def test_polaris_reports_the_memory_mache_says_a_node_has(machine, compiler):
    """
    Whatever mache says a node's memory is, Polaris hands on unchanged.

    A machine that says nothing leaves memory undeclared, which is the
    correct answer rather than a guess: the figure feeds every step's
    default, so inventing one would be worse than having none.
    """
    from polaris import Component

    for _, system in _systems(machine, compiler):
        component = Component(name='ocean')
        component.parallel_system = system
        resources = component.get_available_resources()

        expected = system.get_config_int('memory_per_node') or None
        assert resources['memory_per_node'] == expected
        if expected is None:
            assert resources['memory'] is None
        else:
            assert resources['memory'] == expected * system.nodes


def test_the_machines_phase_a_targets_all_report_their_memory():
    """
    Guard against the memory plumbing above quietly testing nothing.

    Each case degrades gracefully on a machine that says nothing, which is
    right per machine and would be wrong to discover about the whole suite.
    """
    reported = {}
    for machine, compiler in _cases():
        for _, system in _systems(machine, compiler):
            memory = system.get_config_int('memory_per_node')
            if memory:
                reported[machine] = memory
            break
    assert {'chrysalis', 'pm-cpu', 'pm-gpu', 'frontier', 'aurora'} <= set(
        reported
    ), f'machines missing memory_per_node: {reported}'
