from types import SimpleNamespace
from typing import cast

import pytest

from polaris.config import PolarisConfigParser
from polaris.mesh.base import get_base_mesh_step_names
from polaris.mesh.spherical.unified import UNIFIED_MESH_NAMES
from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.realistic_global import add_realistic_global_tasks
from polaris.tasks.ocean.realistic_global.analysis_output import (
    AnalysisOutputForward,
)
from polaris.tasks.ocean.realistic_global.analysis_output.forward import (
    MONTHLY_FILE_TEMPLATES,
    get_monthly_filenames,
)
from polaris.tasks.ocean.realistic_global.forward import (
    DatabaseInitialCondition,
    ForwardStage,
    StepInitialCondition,
)
from polaris.tasks.ocean.realistic_global.forward.tasks import CACHED_MESHES
from polaris.yaml import PolarisYaml

PACKAGE = 'polaris.tasks.ocean.realistic_global.analysis_output'

INIT_MESHES = sorted(get_base_mesh_step_names()) + sorted(UNIFIED_MESH_NAMES)


def _one_year_task(mesh_name, model='omega'):
    """The registered one-year task, with its config combined for ``model``"""
    component = Ocean()
    add_realistic_global_tasks(component=component)
    subdir = f'spherical/realistic_global/{mesh_name}/analysis_output/1_year'
    task = component.tasks[subdir]
    config = task.config
    config.add_from_package('polaris.ocean', 'ocean.cfg')
    config.set('ocean', 'model', model)
    config.combine()
    return task


def _model_config_entry(step, package, yaml):
    """The replacements a step's dynamic model config gave ``yaml``"""
    for entry in step.model_config_data:
        if entry.get('package') == package and entry.get('yaml') == yaml:
            return entry['replacements']
    raise AssertionError(f'{package}/{yaml} was not added to {step.name}')


def test_monthly_files_are_named_for_the_following_month():
    """
    Omega names a monthly file for the time it is written, the start of the
    next month, so a year from 0001-01-01 runs from 0001-02 to 0002-01.
    """
    names = get_monthly_filenames('{year:04d}-{month:02d}')
    assert names == [f'0001-{month:02d}' for month in range(2, 13)] + [
        '0002-01'
    ]


@pytest.mark.parametrize('mesh_name', sorted(CACHED_MESHES))
def test_one_year_task_is_registered_on_each_cached_mesh(mesh_name):
    task = _one_year_task(mesh_name)
    assert list(task.steps) == ['forward', 'global_stats']
    assert task.steps_to_run == ['forward']

    forward = task.steps['forward']
    assert isinstance(forward, AnalysisOutputForward)
    assert forward.subdir == (
        f'spherical/realistic_global/{mesh_name}/analysis_output/1_year/'
        f'forward'
    )
    # every monthly file is an output, so a missing month fails the step
    expected = []
    for template in MONTHLY_FILE_TEMPLATES:
        expected.extend(get_monthly_filenames(template))
    assert len(expected) == 3 * 12
    assert sorted(forward.outputs) == sorted(expected)
    assert 'monthly_means_1MonthTimeStats.0001-02.nc' in forward.outputs
    assert 'moc_1MonthTimeStats.0002-01.nc' in forward.outputs
    # Omega does not make the directory the monthly snapshots go in
    assert forward.stream_dirs == ['output']


@pytest.mark.parametrize('mesh_name', sorted(CACHED_MESHES))
def test_every_monthly_file_is_compared_with_a_baseline(mesh_name):
    """
    Each kind of monthly file is compared with a baseline: the snapshots'
    state, and the time means under Omega's own names, since they have no
    counterparts in the variable map.
    """
    forward = _one_year_task(mesh_name).steps['forward']
    assert sorted(forward.validate_vars) == sorted(forward.outputs)

    snapshot = forward.validate_vars['output/ocn.hist.0002-01.nc']
    assert {'temperature', 'salinity', 'normalVelocity'} <= set(snapshot)

    means = forward.validate_vars['monthly_means_1MonthTimeStats.0001-02.nc']
    assert 'Temperature_TimeMean1Month' in means
    assert 'PseudoThickness_TimeMean1Month' in means

    moc = forward.validate_vars['moc_1MonthTimeStats.0002-01.nc']
    assert moc == ['MOC_streamfunction_Global_TimeMean1Month']


def test_one_year_task_runs_from_a_cached_initial_condition():
    forward = _one_year_task('QU.240km').steps['forward']
    assert isinstance(forward.init_condition, DatabaseInitialCondition)


@pytest.mark.parametrize('mesh_name', INIT_MESHES)
def test_one_year_task_is_registered_on_each_init_mesh(mesh_name):
    """
    Every mesh the init workflow builds gets a one-year task, which runs from
    the initial condition the shared init steps produce, as its forward tasks
    do.
    """
    task = _one_year_task(mesh_name)
    forward = task.steps['forward']
    assert isinstance(forward, AnalysisOutputForward)
    assert isinstance(forward.init_condition, StepInitialCondition)
    assert 'initial_state' in task.steps
    assert 'forcing' in task.steps
    assert task.steps_to_run[-1] == 'forward'
    assert 'global_stats' not in task.steps_to_run
    assert task.config.get('realistic_global_forward', 'run_duration') == (
        '0365_00:00:00'
    )


@pytest.mark.parametrize(
    'mesh_name, moc_num_bins',
    [
        ('QU.240km', 60),
        ('EC30to60E2r2', 180),
        ('qu240km', 60),
        ('icos240km', 60),
        ('u-oi240-lr240', 60),
        ('u-oi30-lr10', 180),
        ('icos30km', 180),
    ],
)
def test_one_year_moc_bins_default_to_omegas(mesh_name, moc_num_bins):
    """
    The MOC has Omega's one-degree bins unless the mesh is coarser than that
    """
    task = _one_year_task(mesh_name)
    assert task.config.getint('analysis_output', 'moc_num_bins') == (
        moc_num_bins
    )


@pytest.mark.parametrize(
    'mesh_name, dt, btr_dt, moc_num_bins',
    [
        ('QU.240km', '01:00:00', '00:03:00', 60),
        ('EC30to60E2r2', '00:30:00', '00:01:00', 180),
    ],
)
def test_one_year_run_is_a_split_explicit_year(
    mesh_name, dt, btr_dt, moc_num_bins
):
    """
    The run is a year of the split-explicit default, on the time steps the
    mesh config gives, with the monthly output over the forward step's own
    and the mesh config's MOC bins.
    """
    task = _one_year_task(mesh_name)
    stage = ForwardStage.from_config(task.config)
    assert stage.run_duration == '0365_00:00:00'

    step = task.steps['forward']
    step.dynamic_model_config(at_setup=True)
    replacements = _model_config_entry(
        step, 'polaris.tasks.ocean.realistic_global.forward', 'forward.yaml'
    )
    assert replacements['time_integrator'] == 'SplitExplicitRK2'
    assert replacements['dt'] == dt
    assert replacements['btr_dt'] == btr_dt

    monthly = _model_config_entry(step, PACKAGE, 'monthly_output.yaml')
    assert monthly == dict(moc_num_bins=moc_num_bins)
    # the monthly output has to come after the forward step's yaml, so that
    # its history and restart streams win
    yamls = [entry.get('yaml') for entry in step.model_config_data]
    assert yamls.index('monthly_output.yaml') > yamls.index('forward.yaml')


def test_monthly_output_yaml_renders():
    yaml = PolarisYaml.read(
        filename='monthly_output.yaml',
        package=PACKAGE,
        replacements=dict(moc_num_bins=60),
        model='Omega',
    )
    analysis = yaml.configs['Analysis']
    assert analysis['MonthlyAverages']['ReductionPeriod'] == ['1Month']
    assert analysis['MOC']['NumBins'] == 60
    assert analysis['MOC']['ReductionPeriod'] == ['1Month']
    streams = yaml.configs['IOStreams']
    assert streams['History']['Filename'].startswith('output/')
    # a monthly reduction needs a restart interval in months
    assert streams['RestartWrite']['FreqUnits'] == 'months'


def test_one_year_run_rejects_mpas_ocean():
    config = PolarisConfigParser()
    config.add_section('ocean')
    config.set('ocean', 'model', 'mpas-ocean')
    step = SimpleNamespace(config=config)
    with pytest.raises(ValueError, match='only Omega'):
        AnalysisOutputForward.setup(cast(AnalysisOutputForward, step))
