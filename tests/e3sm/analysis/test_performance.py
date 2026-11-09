import gzip

import numpy as np
import pytest

from polaris.e3sm.analysis import performance
from polaris.e3sm.analysis.performance import (
    date_to_days,
    find_timing_files,
    read_node_memory,
    read_root_memory,
    read_segment,
    read_slurm_jobs,
    read_wall_clock_stamps,
    select_segment_logs,
)
from polaris.tasks.e3sm.analysis.misomip.performance import _run_time_parts

LID1 = '1322390.261104-131443'
LID2 = '1322427.261104-143415'

SUMMARY = """---------------- TIMING PROFILE ---------------------
  Case        : case
  LID         : {lid}
  total pes active           : 128
  mpi tasks per node         : 64
  pe count for cost estimate : 64

  Overall Metrics:
    Model Cost:             978.59   pe-hrs/simulated_year
    Model Throughput:         1.57   simulated_years/day

    Init Time   :       6.925 seconds
    Run Time    :    4675.119 seconds      150.810 seconds/day
    Final Time  :      12.509 seconds

    TOT Run Time:    4675.119 seconds      150.810 seconds/mday         1.57 myears/wday
    CPL Run Time:       3.250 seconds        0.105 seconds/mday      2257.87 myears/wday
    OCN Run Time:    4410.988 seconds      142.290 seconds/mday         1.66 myears/wday
    GLC Run Time:     260.432 seconds        8.401 seconds/mday        28.18 myears/wday
    CPL COMM Time:      4.302 seconds        0.139 seconds/mday      1705.74 myears/wday
"""  # noqa: E501

STATS = """name                                       on  processes  threads        count      walltotal   wallmax (proc   thrd  )   wallmin (proc   thrd  )
"o:time integration"                        -         64       64 7.137600e+06   2.1e+05  3346.473 (    36      0)  3300.000 (    62      0)
"o:analysis_compute"                        -         64       64 7.137600e+06   1.2e+04   202.394 (    36      0)   200.000 (    62      0)
"o:analysis_write"                          -         64       64 7.137600e+06   1.9e+04   314.125 (    36      0)   300.000 (    62      0)
"g:velocity solve"                          -         64       64 5.952000e+03   1.6e+04   255.776 (    36      0)   255.723 (    29      0)
"g:velocity_solver_extrude_3d_grid"         -         64       64 5.952000e+03   4.7e+03    73.390 (    40      0)    73.387 (    21      0)
"""  # noqa: E501


def _clock(curr, stop):
    return [
        '(seq_timemgr_clockPrint) Clock = drv            1',
        '(seq_timemgr_clockPrint)   Start Time  =     00010101   00000',
        f'(seq_timemgr_clockPrint)   Curr Time   =     {curr}   00000',
        f'(seq_timemgr_clockPrint)   Stop Time   =     {stop}   00000',
    ]


def _stamp(ymd, wall, dt):
    return (
        f' tStamp_write: model date =   {ymd}       0 wall clock = '
        f'{wall} avg dt =   {dt:6.2f} dt =   {dt:6.2f}'
    )


def _memory(ymd, highwater, usage):
    return (
        f' memory_write: model date =   {ymd}       0 memory =    '
        f'{highwater:7.2f} MB (highwater)       {usage:7.2f} MB (usage)  '
        f'(pe=    0 comps= cpl ATM LND ICE OCN GLC ROF WAV IAC ESP)'
    )


def _write(path, lines, compress=False):
    text = '\n'.join(lines) + '\n'
    if compress:
        with gzip.open(path, 'wt') as handle:
            handle.write(text)
    else:
        path.write_text(text)
    return str(path)


@pytest.fixture
def case(tmp_path):
    """A case with two segments: the first a month, compressed, the second
    a run of 2 days after it"""
    timing = tmp_path / 'timing'
    timing.mkdir()
    # the second segment's summary is written first, so the order must come
    # from the LIDs
    _write(timing / f'e3sm_timing.case.{LID2}', [SUMMARY.format(lid=LID2)])
    _write(timing / f'e3sm_timing.case.{LID1}', [SUMMARY.format(lid=LID1)])
    _write(
        timing / f'e3sm_timing_stats.{LID1}.gz',
        STATS.splitlines(),
        compress=True,
    )
    log1 = _write(
        tmp_path / f'cpl.log.{LID1}.gz',
        _clock('00010101', '00010201')
        + [
            _memory('00010101', 863.5, 863.5),
            _stamp('00010102', '2026-11-04 13:17:19', 134.59),
            _memory('00010102', 1529.0, 1215.4),
            _stamp('00010103', '2026-11-04 13:19:42', 143.0),
            _stamp('00010201', '2026-11-04 14:32:57', 159.4),
            _memory('00010201', 1920.6, 1920.6),
        ],
        compress=True,
    )
    log2 = _write(
        tmp_path / f'cpl.log.{LID2}',
        _clock('00010201', '00010301')
        + [
            _memory('00010201', 602.5, 602.5),
            _stamp('00010202', '2026-11-04 14:40:00', 150.0),
            _stamp('00010203', '2026-11-04 14:42:30', 150.0),
        ],
    )
    return tmp_path, [log1, log2]


def test_a_segment_s_throughput_cost_and_run_times(case):
    case_dir, logs = case
    summary, stats = find_timing_files(str(case_dir))[LID1]
    segment = read_segment(summary, stats, logs[0])
    assert segment.job_id == '1322390'
    assert segment.throughput == 1.57
    assert segment.cost == 978.59
    assert segment.cost_pes == 64
    assert segment.init_time == 6.925
    assert segment.final_time == 12.509
    assert segment.component_times['OCN'] == 4410.988
    assert segment.component_times['CPL COMM'] == 4.302
    assert segment.timers['g:velocity solve'] == 255.776


def test_a_segment_s_period_runs_from_its_clock_to_its_last_stamp(case):
    case_dir, logs = case
    summary, stats = find_timing_files(str(case_dir))[LID1]
    segment = read_segment(summary, stats, logs[0])
    assert segment.start_day == 0.0
    assert segment.end_day == 31.0


def test_timing_files_are_in_the_order_the_segments_ran(case):
    case_dir, _ = case
    files = find_timing_files(str(case_dir))
    assert list(files) == [LID1, LID2]
    assert files[LID2][1] is None


def test_the_first_day_of_each_segment_has_a_throughput(case):
    _, logs = case
    stamps = read_wall_clock_stamps(logs)
    np.testing.assert_allclose(stamps.days, [1.0, 2.0, 31.0, 32.0, 33.0])
    # the month's last stamp comes 29 days after the one before
    np.testing.assert_allclose(
        stamps.seconds_per_day,
        [134.59, 143.0, 159.4 / 29.0, 150.0, 150.0],
    )
    assert stamps.lids[-1] == LID2


def test_a_day_run_again_is_taken_from_the_later_segment(case, tmp_path):
    _, logs = case
    rerun = _write(
        tmp_path / 'cpl.log.1322500.261104-160000',
        _clock('00010201', '00010301')
        + [_stamp('00010202', '2026-11-04 16:03:00', 180.0)],
    )
    stamps = read_wall_clock_stamps(logs + [rerun])
    index = list(stamps.days).index(32.0)
    assert stamps.lids[index] == '1322500.261104-160000'
    assert stamps.seconds_per_day[index] == 180.0


def test_each_segment_keeps_its_own_memory_records(case):
    _, logs = case
    memory = read_root_memory(logs)
    # the first segment's end and the second's start share a model time
    at_month_end = memory.highwater[memory.days == 31.0]
    np.testing.assert_allclose(at_month_end, [1920.6, 602.5])
    assert memory.lids == [LID1, LID1, LID1, LID2]


def test_node_memory_is_read_from_the_coupler_node_s_columns(tmp_path):
    header = (
        '#TOD, VSZ_CPL_N_0, RSS_CPL_N_0, VSZ_ATM_N_0, RSS_ATM_N_0, '
        'VSZ_GLC_N_1, RSS_GLC_N_1'
    )
    profile = _write(
        tmp_path / f'memory.3.86400.log.{LID1}.gz',
        [
            header,
            '   10101.00000,    45377.727,    45000.0,  1.0,  2.0, 3.0, 4.0',
            '   10201.50000,   104376.480,   101263.441, 1.0, 2.0, 3.0, 4.0',
        ],
        compress=True,
    )
    memory = read_node_memory([profile])
    np.testing.assert_allclose(memory.days, [0.0, 31.5])
    np.testing.assert_allclose(memory.highwater, [45377.727, 104376.480])
    np.testing.assert_allclose(memory.usage, [45000.0, 101263.441])
    glc = read_node_memory([profile], column='GLC')
    np.testing.assert_allclose(glc.highwater, [3.0, 3.0])


def test_run_time_parts_add_up_to_the_total(case):
    case_dir, logs = case
    summary, stats = find_timing_files(str(case_dir))[LID1]
    parts = _run_time_parts(read_segment(summary, stats, logs[0]))
    assert sum(parts.values()) == pytest.approx(4675.119)
    assert parts['MALI: FEM grid build'] == 73.390
    assert parts['MALI: rest of velocity solve'] == pytest.approx(182.386)
    assert parts['ocean: other'] == pytest.approx(
        4410.988 - 3346.473 - 202.394 - 314.125
    )


def test_a_timer_that_never_ran_took_no_time(case):
    case_dir, logs = case
    summary, stats = find_timing_files(str(case_dir))[LID1]
    segment = read_segment(summary, stats, logs[0])
    timers = dict(segment.timers)
    solve = timers['g:velocity solve']
    del timers['g:velocity_solver_extrude_3d_grid']
    parts = _run_time_parts(segment._replace(timers=timers))
    assert 'MALI: FEM grid build' not in parts
    assert parts['MALI: rest of velocity solve'] == solve
    assert sum(parts.values()) == pytest.approx(4675.119)


def test_without_timers_each_model_s_run_time_is_one_part(case):
    case_dir, logs = case
    summary, stats = find_timing_files(str(case_dir))[LID2]
    parts = _run_time_parts(read_segment(summary, stats, logs[1]))
    assert list(parts) == ['ocean: other', 'MALI: other', 'coupler and driver']
    assert parts['ocean: other'] == 4410.988
    assert sum(parts.values()) == pytest.approx(4675.119)


def test_slurm_is_skipped_where_sacct_is_missing(monkeypatch):
    monkeypatch.setattr(performance.shutil, 'which', lambda name: None)
    assert read_slurm_jobs(['1322390']) == {}


def test_slurm_jobs_give_queue_waits_and_the_largest_task_memory(
    monkeypatch,
):
    output = (
        '1322390|2026-11-04T13:13:34|2026-11-04T13:14:40|'
        '2026-11-04T14:33:14|\n'
        '1322390.batch|2026-11-04T13:14:40|2026-11-04T13:14:40|'
        '2026-11-04T14:33:14|45285K\n'
        '1322390.0|2026-11-04T13:14:53|2026-11-04T13:14:53|'
        '2026-11-04T14:33:11|1849543K\n'
        '1322427|2026-11-04T14:33:20|Unknown|Unknown|\n'
    )

    class Result:
        stdout = output

    monkeypatch.setattr(performance.shutil, 'which', lambda name: name)
    monkeypatch.setattr(
        performance.subprocess, 'run', lambda *args, **kwargs: Result()
    )
    jobs = read_slurm_jobs(['1322390', '1322427'])
    assert list(jobs) == ['1322390']
    assert jobs['1322390'].queue_wait == 66.0
    assert jobs['1322390'].elapsed == 4714.0
    assert jobs['1322390'].max_rss == pytest.approx(1849543.0 / 1024.0)


def test_driver_dates_are_days_since_the_start_of_year_1():
    assert date_to_days('00010101') == 0.0
    assert date_to_days('00020301', 43200) == 365.0 + 59.0 + 0.5


def test_only_segments_that_start_in_the_period_are_selected(case, tmp_path):
    """The first segment starts in January, the second in February; a log
    without its clock yet is left out"""
    _, logs = case
    starting = _write(tmp_path / 'cpl.log.1322500.261104-150000', ['init'])
    january = date_to_days('00010101')
    february = date_to_days('00010201')
    march = date_to_days('00010301')
    every = logs + [starting]
    assert select_segment_logs(every, january, february) == [logs[0]]
    assert select_segment_logs(every, february, march) == [logs[1]]
    assert select_segment_logs(every, january, march) == logs
