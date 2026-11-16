import numpy as np

from polaris.tasks.e3sm.analysis.misomip.centerline import (
    _date_text,
    pick_landice_records,
    pick_snapshot_days,
)


def test_a_frame_is_dated_by_the_end_of_its_month():
    """The month ending at the start of year 18, and noon on 1 March of
    year 1"""
    assert _date_text(17 * 365.0) == '0018-01-01'
    assert _date_text(59.0) == '0001-03-01'


def test_each_month_gets_mali_s_latest_record_at_or_before_its_end():
    """MALI writes every 10 days and a restart writes day 30 again; each
    month's end takes the record before it, and a month before MALI's
    first record gets none"""
    record_days = np.array([10.0, 20.0, 30.0, 30.0, 40.0, 50.0, 59.0])
    records = pick_landice_records([0.0, 31.0, 59.0], record_days)
    assert records == {31.0: 2, 59.0: 6}


def test_snapshots_are_spread_over_the_run_with_its_ends():
    """Five of eleven yearly snapshots, the first and last included, the
    earlier day where two are as near; every one of three"""
    days = [365.0 * year for year in range(11)]
    assert pick_snapshot_days(days) == [0.0, 730.0, 1825.0, 2555.0, 3650.0]
    assert pick_snapshot_days(days[:3]) == days[:3]
