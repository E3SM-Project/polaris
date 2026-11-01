import os

import pytest

from polaris import Component
from polaris.tasks.e3sm.analysis.misomip import add_misomip_analysis_tasks
from tests.e3sm.analysis.test_case import _write_case

MESH = 'misomip-o4km-li1km'
TASK = f'{MESH}/misomip/ocean0'

STREAMS = """<streams>
<stream name="timeSeriesStatsMonthlyOutput"
        type="output"
        filename_template="{prefix}timeSeriesStatsMonthly.$Y-$M-$D.nc"
        output_interval="00-01-00_00:00:00">
</stream>
<stream name="globalStatsOutput"
        type="output"
        filename_template="{prefix}globalStats.$Y-$M-$D.nc"
        output_interval="00-00-01_00:00:00">
</stream>
</streams>
"""

NAMELIST = """&wetting_drying
    config_drying_min_cell_height = 1.0d-3
/
"""


def _write_run(run_dir, prefix, months, namelist):
    os.makedirs(run_dir, exist_ok=True)
    with open(os.path.join(run_dir, 'streams.ocean'), 'w') as out:
        out.write(STREAMS.format(prefix=prefix))
    with open(os.path.join(run_dir, namelist), 'w') as out:
        out.write(NAMELIST)
    for month in months:
        for stream in ['timeSeriesStatsMonthly', 'globalStats']:
            name = f'{prefix}{stream}.0001-{month:02d}-01.nc'
            with open(os.path.join(run_dir, name), 'w'):
                pass


def _standalone_run(tmp_path, months):
    work_dir = str(tmp_path / 'forward')
    _write_run(work_dir, 'mpaso.hist.am.', months, 'namelist.ocean')
    with open(os.path.join(work_dir, 'init.nc'), 'w'):
        pass
    return work_dir


def _e3sm_case(tmp_path, months, budgets):
    case_dir = str(tmp_path / 'case')
    run_dir = str(tmp_path / 'run')
    _write_case(
        case_dir,
        {
            'env_run.xml': {
                'CASE': 'case',
                'RUNDIR': run_dir,
                'DOUT_S_ROOT': str(tmp_path / 'archive'),
                'MPASO_IC_FILE': str(tmp_path / 'ic.nc'),
                'BUDGETS': budgets,
            }
        },
    )
    _write_run(run_dir, 'case.mpaso.hist.am.', months, 'mpaso_in')
    with open(os.path.join(run_dir, 'cpl.log.1.gz'), 'w'):
        pass
    return case_dir


def _configure(tmp_path, e3sm_case=None, standalone=None):
    component = Component(name='e3sm/analysis')
    add_misomip_analysis_tasks(component)
    task = component.tasks[TASK]
    section = f'misomip_analysis_{MESH}'
    if e3sm_case is not None:
        task.config.set(section, 'ocean0_e3sm_case', e3sm_case, user=True)
    if standalone is not None:
        task.config.set(section, 'ocean0_standalone', standalone, user=True)
    task.configure()
    return task


def test_each_run_gets_steps_named_for_its_months(tmp_path):
    """Both runs give diagnostics and plots, a comparison, the conservation
    of the run with budgets, and the publish step that depends on the
    steps that make products."""
    task = _configure(
        tmp_path,
        e3sm_case=_e3sm_case(tmp_path, months=[1, 2], budgets='TRUE'),
        standalone=_standalone_run(tmp_path, months=[1]),
    )

    assert sorted(step.subdir for step in task.steps.values()) == [
        f'{TASK}/comparison_0001-01_0001-02_0001-01_0001-01',
        f'{TASK}/e3sm/conservation_0001-01_0001-02',
        f'{TASK}/e3sm/diagnostics_0001-01_0001-02',
        f'{TASK}/e3sm/plots_0001-01_0001-02',
        f'{TASK}/publish',
        f'{TASK}/standalone/diagnostics_0001-01_0001-01',
        f'{TASK}/standalone/plots_0001-01_0001-01',
    ]
    diagnostics = task.steps['e3sm_diagnostics']
    assert diagnostics.min_thickness == 1.0e-3
    assert len(diagnostics.monthly_filenames) == 2
    assert len(diagnostics.daily_filenames) == 2
    publish = task.steps['publish']
    prefix = TASK.replace('/', '_')
    assert sorted(publish.dependencies) == [
        f'{prefix}_comparison_0001-01_0001-02_0001-01_0001-01',
        f'{prefix}_e3sm_conservation_0001-01_0001-02',
        f'{prefix}_e3sm_plots_0001-01_0001-02',
        f'{prefix}_standalone_plots_0001-01_0001-01',
    ]
    # setup gives each step its task's config
    publish.config = task.config
    publish.base_work_dir = str(tmp_path / 'work')
    assert publish.output_path() == str(
        tmp_path / 'work' / 'analysis_output' / MESH / 'ocean0'
    )


def test_a_case_without_budgets_has_no_conservation_step(tmp_path):
    task = _configure(
        tmp_path, e3sm_case=_e3sm_case(tmp_path, months=[1], budgets='FALSE')
    )

    assert sorted(task.steps) == ['e3sm_diagnostics', 'e3sm_plots', 'publish']


def test_a_task_without_runs_fails_at_setup(tmp_path):
    """Every task sharing the config is configured, so configuring one
    without runs is not an error; setting it up is."""
    task = _configure(tmp_path)

    assert list(task.steps) == ['publish']
    with pytest.raises(ValueError, match='ocean0_e3sm_case or'):
        task.steps['publish'].setup()


def test_runs_over_the_same_months_get_distinct_steps(tmp_path):
    """The first comparison of E3SM with a standalone run covers the same
    month in both."""
    task = _configure(
        tmp_path,
        e3sm_case=_e3sm_case(tmp_path, months=[1], budgets='FALSE'),
        standalone=_standalone_run(tmp_path, months=[1]),
    )

    assert sorted(task.steps) == [
        'comparison',
        'e3sm_diagnostics',
        'e3sm_plots',
        'publish',
        'standalone_diagnostics',
        'standalone_plots',
    ]
