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
    assert sorted(tasks) == sorted(expected)


def test_physics_of_each_task():
    tasks = _get_isomip_plus_tasks()
    com_paths = [path for path, task in tasks.items() if task.variant == 'com']
    assert sorted(tasks[path].experiment for path in com_paths) == sorted(
        3 * ['ocean0', 'ocean1', 'ocean2']
    )
    for task in tasks.values():
        config = task.config
        if task.variant == 'com':
            assert config.get('isomip_plus', 'physics') == 'com'
            assert config.get('ocean', 'eos_type') == 'linear'
            assert config.getfloat('ocean', 'eos_linear_alpha') == 0.03836
        else:
            assert config.get('isomip_plus', 'physics') == 'e3sm'
            assert config.get('ocean', 'eos_type') == 'teos-10'


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
