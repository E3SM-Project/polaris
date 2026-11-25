import pytest

from polaris.ocean.ice_shelf import add_wetting_drying_yaml_files
from polaris.yaml import PolarisYaml


class _RecordingStep:
    """A stand-in for a model step that records the yaml files added"""

    def __init__(self):
        self.yaml_files = []

    def add_yaml_file(self, package, yaml):
        self.yaml_files.append((package, yaml))


@pytest.mark.parametrize(
    'thin_film, split_explicit, expected',
    [
        (False, False, ['wetting_drying.yaml']),
        (False, True, ['wetting_drying.yaml', 'split_explicit.yaml']),
        (
            True,
            False,
            ['wetting_drying.yaml', 'thin_film_wetting_drying.yaml'],
        ),
        (
            True,
            True,
            [
                'wetting_drying.yaml',
                'split_explicit.yaml',
                'thin_film_wetting_drying.yaml',
            ],
        ),
    ],
)
def test_add_wetting_drying_yaml_files(thin_film, split_explicit, expected):
    step = _RecordingStep()
    add_wetting_drying_yaml_files(
        step, thin_film=thin_film, split_explicit=split_explicit
    )
    assert step.yaml_files == [
        ('polaris.ocean.ice_shelf', filename) for filename in expected
    ]


@pytest.mark.parametrize(
    'filename',
    [
        'wetting_drying.yaml',
        'split_explicit.yaml',
        'thin_film_wetting_drying.yaml',
    ],
)
def test_wetting_drying_yaml_files_set_no_time_integrator(filename):
    # these files are added after the yaml files that choose the time
    # integrator, so they must not override it
    yaml = PolarisYaml.read(
        filename=filename,
        package='polaris.ocean.ice_shelf',
        model='mpas-ocean',
    )
    options = yaml.configs.get('time_integration', {})
    assert 'config_time_integrator' not in options
