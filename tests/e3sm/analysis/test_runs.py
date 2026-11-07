import os

import pytest

from polaris.e3sm.analysis.runs import (
    StandaloneRun,
    month_range_key,
    select_months,
)
from polaris.streams import StreamFile

STREAMS = """<streams>
<stream name="timeSeriesStatsMonthlyOutput"
        type="output"
        filename_template="analysis_members/mpaso.hist.am.timeSeriesStatsMonthly.$Y-$M-$D.nc"
        output_interval="00-01-00_00:00:00">
</stream>
</streams>
"""

NAMELIST = """&wetting_drying
    config_use_wetting_drying = .true.
    config_drying_min_cell_height = 1.0e-3
/
"""


def _monthly(*months):
    return [
        StreamFile(
            path=f'{year}-{month}', year=year, month=month, day=1, seconds=0
        )
        for year, month in months
    ]


def test_months_are_selected_from_a_range_of_years():
    files = _monthly((1, 12), (2, 1), (2, 2), (3, 1))

    selected = select_months(files, start_year=2, end_year=2)

    assert [(f.year, f.month) for f in selected] == [(2, 1), (2, 2)]
    assert month_range_key(selected) == '0002-01_0002-02'


def test_a_gap_between_months_is_an_error():
    files = _monthly((1, 1), (1, 2), (1, 5))

    with pytest.raises(ValueError, match='0001-03, 0001-04 are missing'):
        select_months(files, start_year=1, end_year=1)


def test_no_months_in_the_range_is_an_error():
    with pytest.raises(ValueError, match='No monthly means'):
        select_months(_monthly((1, 1)), start_year=2, end_year=3)


def test_a_standalone_run_is_read_from_its_forward_step(tmp_path):
    work_dir = tmp_path / 'forward'
    os.makedirs(work_dir / 'analysis_members')
    (work_dir / 'streams.ocean').write_text(STREAMS)
    (work_dir / 'namelist.ocean').write_text(NAMELIST)
    (tmp_path / 'init_target.nc').write_text('')
    os.symlink(tmp_path / 'init_target.nc', work_dir / 'init.nc')
    for month in [1, 2]:
        name = f'mpaso.hist.am.timeSeriesStatsMonthly.0001-{month:02d}-01.nc'
        (work_dir / 'analysis_members' / name).write_text('')

    run = StandaloneRun(str(work_dir))

    files = run.find_stream_files('timeSeriesStatsMonthlyOutput')
    assert [f.month for f in files] == [1, 2]
    assert run.initial_condition == str(tmp_path / 'init_target.nc')
    assert run.namelist_option('config_drying_min_cell_height') == '1.0e-3'


def test_a_directory_that_is_not_a_forward_step_is_an_error(tmp_path):
    with pytest.raises(FileNotFoundError, match='not the work directory'):
        StandaloneRun(str(tmp_path))
