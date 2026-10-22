from importlib import import_module

from polaris.config import PolarisConfigParser
from polaris.tasks.ocean import Ocean

# polaris imports task packages lazily, so import the module itself
isomip_plus = import_module('polaris.tasks.ocean.isomip_plus')


def _get_isomip_plus_tasks():
    """Add the ISOMIP+ tasks to a fresh ocean component"""
    component = Ocean()
    component.tasks = dict()
    isomip_plus.add_isomip_plus_tasks(component)
    return component.tasks


def test_task_paths():
    tasks = _get_isomip_plus_tasks()
    expected = []
    for res in ['4km', '2km', '1km']:
        for experiment in isomip_plus.EXPERIMENTS:
            expected.append(f'planar/isomip_plus/{res}/z-star/{experiment}')
        for variant, experiments in isomip_plus.VARIANTS.items():
            for experiment in experiments:
                expected.append(
                    f'planar/isomip_plus/{res}/z-star/{variant}/{experiment}'
                )
        for variant, experiments in isomip_plus.RESTART_TASKS.items():
            for experiment in experiments:
                expected.append(
                    f'planar/isomip_plus/{res}/z-star/{variant}/'
                    f'{experiment}/with_restart'
                )
    assert sorted(tasks) == sorted(expected)


def test_variant_adds_path_level_and_config(monkeypatch):
    variant = 'test_variant'
    monkeypatch.setattr(isomip_plus, 'VARIANTS', {variant: ['ocean1']})

    # the variant's config file doesn't exist, so record it instead
    added: dict[str, list[str]] = dict()
    original = PolarisConfigParser.add_from_package

    def _add_from_package(self, package, config_filename, exception=True):
        added.setdefault(self.filepath, []).append(config_filename)
        if config_filename != f'{variant}.cfg':
            original(self, package, config_filename, exception)

    monkeypatch.setattr(
        PolarisConfigParser, 'add_from_package', _add_from_package
    )

    tasks = _get_isomip_plus_tasks()

    path = f'planar/isomip_plus/4km/z-star/{variant}/ocean1'
    assert path in tasks
    task = tasks[path]
    assert task.variant == variant
    assert task.experiment == 'ocean1'
    assert task.config.filepath == f'ocean/{path}/isomip_plus.cfg'
    # the variant's config comes last, so it overrides the others
    assert added[task.config.filepath][-1] == f'{variant}.cfg'

    # the default task is still there, without the variant's config
    default_path = 'planar/isomip_plus/4km/z-star/ocean1'
    assert tasks[default_path].variant is None
    default_config = f'ocean/{default_path}/isomip_plus.cfg'
    assert f'{variant}.cfg' not in added[default_config]


def test_split_explicit_tasks():
    tasks = _get_isomip_plus_tasks()
    for res in ['4km', '2km', '1km']:
        vardir = f'planar/isomip_plus/{res}/z-star/split_explicit'
        for experiment in ['ocean0', 'inception', 'wetting', 'drying']:
            path = f'{vardir}/{experiment}'
            task = tasks[path]
            assert task.variant == 'split_explicit'
            # SSH adjustment uses the same scheme as the forward run
            for section in ['isomip_plus_forward', 'ssh_adjustment']:
                assert (
                    task.config.get(section, 'time_integrator')
                    == 'split_explicit'
                )
        for experiment in ['ocean1', 'ocean2']:
            assert f'{vardir}/{experiment}' not in tasks

    # the default tasks still use RK4
    task = tasks['planar/isomip_plus/4km/z-star/wetting']
    for section in ['isomip_plus_forward', 'ssh_adjustment']:
        assert task.config.get(section, 'time_integrator') == 'RK4'


def test_restart_task_shares_init_and_ssh_adjustment():
    tasks = _get_isomip_plus_tasks()
    basedir = 'planar/isomip_plus/4km/z-star/split_explicit/wetting'
    base = tasks[basedir]
    task = tasks[f'{basedir}/with_restart']
    assert task.with_restart
    assert task.name == 'wetting_with_restart'

    # init and SSH adjustment are the base task's own steps
    assert task.steps['init'] is base.steps['init']
    ssh_steps = [name for name in base.steps if name.startswith('ssh_')]
    assert ssh_steps
    for name in ssh_steps:
        assert task.steps[name] is base.steps[name]

    # the restart test has its own runs, compared by a validate step
    for name in ['forward', 'restart', 'validate']:
        assert task.steps[name].path == f'ocean/{basedir}/with_restart/{name}'
    assert task.steps['forward'].restart_test == 'full'
    assert task.steps['restart'].restart_test == 'restart'
    assert 'forward' in task.steps['restart'].dependencies
    assert 'viz' not in task.steps
