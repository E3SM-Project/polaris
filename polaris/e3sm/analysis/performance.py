"""
The performance of an E3SM run, from the files CIME and the driver write
for each job, or segment, of the run

- CIME's timing summary, ``e3sm_timing.<case>.<LID>`` in the case's
  ``timing`` directory, gives the segment's throughput, cost and the run
  time of each component;
- the timer statistics beside it, ``e3sm_timing_stats.<LID>.gz``, give the
  time in each of the models' timers;
- the coupler's log, ``cpl.log.<LID>``, gives the segment's model period,
  the wall-clock time at the end of each model day and the memory of the
  coupler's root task;
- the driver's memory profile, ``memory.<level>.<seconds>.log.<LID>``, gives
  the memory of the nodes of each component's root task, where the case
  turns profiling on.

``<LID>`` is ``<job ID>.<date>-<time>``, so the job ID of each segment comes
from its files' names.
"""

import gzip
import os
import re
import shutil
import subprocess
from datetime import datetime
from typing import NamedTuple

import numpy as np

from polaris.e3sm.analysis.calendar import month_start_days

#: The LID at the end of the name of a segment's files
_LID = re.compile(r'(?P<lid>(?P<job>\d+)\.\d{6}-\d{6})(\.gz)?$')

#: A line of the timing summary's overall metrics
_METRIC = re.compile(
    r'^\s*(?P<name>Model Cost|Model Throughput|Init Time|Run Time|'
    r'Final Time)\s*:\s*(?P<value>[-\d.]+)'
)

#: A line of the timing summary's run times, such as ``OCN Run Time:``
_RUN_TIME = re.compile(
    r'^\s*(?P<name>\w+) (?P<kind>Run|COMM) Time:\s*(?P<seconds>[-\d.]+) '
    r'seconds'
)

#: The summary's pe count for the cost
_COST_PES = re.compile(r'pe count for cost estimate\s*:\s*(?P<pes>\d+)')

#: A timer in the timer statistics: its name, ``on``, the processes and
#: threads, the count, the total over processes and the maximum
_TIMER = re.compile(
    r'^\s*"(?P<name>[^"]+)"\s+\S+\s+\d+\s+\d+\s+(?P<count>\S+)\s+'
    r'(?P<total>\S+)\s+(?P<max>\S+)'
)

#: The coupler's daily wall-clock stamp
_STAMP = re.compile(
    r'tStamp_write: model date =\s*(?P<ymd>\d+)\s+(?P<tod>\d+) wall clock = '
    r'(?P<wall>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})'
    r'.*\bdt =\s*(?P<dt>[-\d.]+)\s*$'
)

#: The memory of the coupler's root task, in MB
_MEMORY = re.compile(
    r'memory_write: model date =\s*(?P<ymd>\d+)\s+(?P<tod>\d+) memory =\s*'
    r'(?P<highwater>[\d.]+) MB \(highwater\)\s+(?P<usage>[\d.]+) MB'
)

#: The driver clock's times when a segment starts
_CLOCK = re.compile(
    r'\(seq_timemgr_clockPrint\)\s+(?P<name>Curr|Stop) Time\s*=\s*'
    r'(?P<ymd>\d+)\s+(?P<tod>\d+)'
)


class Segment(NamedTuple):
    """
    The performance of one segment of an E3SM run

    Attributes
    ----------
    lid : str
        The segment's LID, ``<job ID>.<date>-<time>``

    job_id : str
        The batch job's ID

    start_day, end_day : float
        The segment's model period, in days since 0001-01-01

    throughput : float
        Simulated years per wall-clock day

    cost : float
        Processor hours per simulated year

    cost_pes : int
        The processors the cost counts

    init_time, run_time, final_time : float
        The seconds the segment spends initializing, running and finishing

    component_times : dict
        The run time in seconds of each component, keyed by its name in the
        summary, such as ``OCN``, and ``CPL COMM`` for the coupler's
        communication

    timers : dict
        The largest time in seconds over the processes in each timer of the
        timer statistics, if the segment has them
    """

    lid: str
    job_id: str
    start_day: float
    end_day: float
    throughput: float
    cost: float
    cost_pes: int
    init_time: float
    run_time: float
    final_time: float
    component_times: dict
    timers: dict


class WallClockStamps(NamedTuple):
    """
    The coupler's wall-clock time at the end of each model day

    Attributes
    ----------
    days : numpy.ndarray
        The model time, in days since 0001-01-01

    lids : list of str
        The segment of each stamp

    seconds_per_day : numpy.ndarray
        The wall-clock seconds since the previous stamp, or since the start
        of the segment's run loop, over the model days since then
    """

    days: np.ndarray
    lids: list
    seconds_per_day: np.ndarray


class Memory(NamedTuple):
    """
    The memory of the coupler's root task at each of the driver's records

    Attributes
    ----------
    days : numpy.ndarray
        The model time, in days since 0001-01-01

    lids : list of str
        The LID of the segment that wrote each record

    highwater, usage : numpy.ndarray
        The task's high-water mark and current use, in MB
    """

    days: np.ndarray
    lids: list
    highwater: np.ndarray
    usage: np.ndarray


class Job(NamedTuple):
    """
    A segment's batch job, as Slurm accounts for it

    Attributes
    ----------
    job_id : str
        The job's ID

    queue_wait : float
        The seconds from submission to start

    elapsed : float
        The seconds from start to end, NaN if the job hasn't ended

    max_rss : float
        The largest resident memory of any task in the job's steps, in MB
    """

    job_id: str
    queue_wait: float
    elapsed: float
    max_rss: float


def find_lid(filename):
    """
    Get the LID at the end of a segment's file name

    Parameters
    ----------
    filename : str
        A file such as ``cpl.log.1322390.261104-131443.gz``

    Returns
    -------
    lid : str or None
        The LID, or None if the name doesn't end with one
    """
    match = _LID.search(os.path.basename(filename))
    return None if match is None else match.group('lid')


def find_timing_files(case_dir):
    """
    Find the timing summary and timer statistics of each segment

    Parameters
    ----------
    case_dir : str
        The case directory

    Returns
    -------
    files : dict
        For each LID, in the order of the segments, the summary's path and
        the statistics' path, or None if they are missing
    """
    timing_dir = os.path.join(case_dir, 'timing')
    files: dict = {}
    if not os.path.isdir(timing_dir):
        return files
    for name in sorted(os.listdir(timing_dir)):
        lid = find_lid(name)
        if lid is None or not name.startswith('e3sm_timing.'):
            continue
        stats = os.path.join(timing_dir, f'e3sm_timing_stats.{lid}.gz')
        files[lid] = (
            os.path.join(timing_dir, name),
            stats if os.path.exists(stats) else None,
        )
    return dict(sorted(files.items(), key=lambda item: _lid_order(item[0])))


def read_segment(summary_filename, stats_filename, log_filename):
    """
    Read a segment's performance

    Parameters
    ----------
    summary_filename : str
        CIME's timing summary of the segment

    stats_filename : str or None
        The timer statistics of the segment, if it has them

    log_filename : str
        The coupler's log of the segment, for its model period

    Returns
    -------
    segment : Segment
        The segment's performance
    """
    lid = find_lid(summary_filename)
    if lid is None:
        raise ValueError(f'{summary_filename} does not end with an LID.')
    metrics: dict[str, float] = {}
    component_times: dict[str, float] = {}
    cost_pes = None
    for line in _read_lines(summary_filename):
        match = _METRIC.match(line)
        if match is not None:
            metrics.setdefault(match.group('name'), float(match['value']))
            continue
        match = _RUN_TIME.match(line)
        if match is not None:
            name = match.group('name')
            if match.group('kind') == 'COMM':
                name = f'{name} COMM'
            component_times[name] = float(match.group('seconds'))
            continue
        match = _COST_PES.search(line)
        if match is not None:
            cost_pes = int(match.group('pes'))
    missing = [
        name
        for name in [
            'Model Cost',
            'Model Throughput',
            'Init Time',
            'Run Time',
            'Final Time',
        ]
        if name not in metrics
    ]
    if missing or cost_pes is None:
        raise ValueError(
            f'{summary_filename} is not a complete timing summary: it '
            f'lacks {", ".join(missing) or "the pe count for the cost"}.'
        )
    start_day, end_day = read_segment_period(log_filename)
    timers = {} if stats_filename is None else read_timers(stats_filename)
    return Segment(
        lid=lid,
        job_id=lid.split('.')[0],
        start_day=start_day,
        end_day=end_day,
        throughput=metrics['Model Throughput'],
        cost=metrics['Model Cost'],
        cost_pes=cost_pes,
        init_time=metrics['Init Time'],
        run_time=metrics['Run Time'],
        final_time=metrics['Final Time'],
        component_times=component_times,
        timers=timers,
    )


def read_timers(filename):
    """
    Read the largest time over the processes in each timer

    Parameters
    ----------
    filename : str
        The timer statistics, ``e3sm_timing_stats.<LID>``, compressed or not

    Returns
    -------
    timers : dict
        The seconds in each timer, keyed by its name, such as
        ``o:time integration``.  A timer listed more than once keeps its
        first entry, from the driver's root task's tree.
    """
    timers: dict = {}
    for line in _read_lines(filename):
        match = _TIMER.match(line)
        if match is None:
            continue
        try:
            seconds = float(match.group('max'))
        except ValueError:
            continue
        timers.setdefault(match.group('name'), seconds)
    return timers


def read_segment_period(log_filename):
    """
    Read a segment's model period from its coupler log: from the driver
    clock's time at the start to the last daily stamp, or to the clock's
    stop time if the segment has no stamps yet

    Parameters
    ----------
    log_filename : str
        The coupler's log

    Returns
    -------
    start_day, end_day : float
        Days since 0001-01-01
    """
    start = None
    stop = None
    last_stamp = None
    for line in _read_lines(log_filename):
        match = _CLOCK.search(line)
        if match is not None:
            day = date_to_days(match.group('ymd'), match.group('tod'))
            if match.group('name') == 'Curr' and start is None:
                start = day
            elif match.group('name') == 'Stop' and stop is None:
                stop = day
            continue
        match = _STAMP.search(line)
        if match is not None:
            last_stamp = date_to_days(match.group('ymd'), match.group('tod'))
    if start is None:
        raise ValueError(f'{log_filename} has no driver clock.')
    end = last_stamp if last_stamp is not None else stop
    return start, end


def read_wall_clock_stamps(log_filenames):
    """
    Read the coupler's daily wall-clock stamps from each segment's log

    Parameters
    ----------
    log_filenames : list of str
        The coupler's logs, in the order they were written

    Returns
    -------
    stamps : WallClockStamps
        The stamps, a model day written again by a later segment (after a
        rerun from a restart) taken from the later one
    """
    records: dict = {}
    for filename in log_filenames:
        lid = find_lid(filename)
        previous = None
        for line in _read_lines(filename):
            if previous is None:
                match = _CLOCK.search(line)
                if match is not None and match.group('name') == 'Curr':
                    previous = date_to_days(
                        match.group('ymd'), match.group('tod')
                    )
                    continue
            match = _STAMP.search(line)
            if match is None:
                continue
            day = date_to_days(match.group('ymd'), match.group('tod'))
            # the coupler's dt is the wall-clock time since its last stamp,
            # or since the run loop started for the first
            rate = np.nan
            if previous is not None and day > previous:
                rate = float(match.group('dt')) / (day - previous)
            records[day] = (lid, rate)
            previous = day
    days = np.array(sorted(records))
    return WallClockStamps(
        days=days,
        lids=[records[day][0] for day in days],
        seconds_per_day=np.array([records[day][1] for day in days]),
    )


def read_root_memory(log_filenames):
    """
    Read the memory of the coupler's root task from each segment's log

    Parameters
    ----------
    log_filenames : list of str
        The coupler's logs, in the order they were written

    Returns
    -------
    memory : Memory
        The task's memory at each record, in the order written.  Each
        segment starts new processes, so the last record of one segment and
        the first of the next share a model time but not a memory.
    """
    records = []
    for filename in log_filenames:
        lid = find_lid(filename)
        for line in _read_lines(filename):
            match = _MEMORY.search(line)
            if match is None:
                continue
            records.append(
                (
                    date_to_days(match.group('ymd'), match.group('tod')),
                    lid,
                    float(match.group('highwater')),
                    float(match.group('usage')),
                )
            )
    return _memory(records)


def read_node_memory(filenames, column='CPL'):
    """
    Read the memory of the node of a component's root task from the
    driver's memory profiles, written at profiling level 3

    Parameters
    ----------
    filenames : list of str
        The profiles, ``memory.3.<seconds>.log.<LID>``, in the order they
        were written

    column : str, optional
        The component whose root task's node to read, such as ``CPL`` or
        ``GLC``

    Returns
    -------
    memory : Memory
        The node's memory, summed over its tasks, in MB, at each record in
        the order written
    """
    records = []
    for filename in filenames:
        lid = find_lid(filename)
        lines = _read_lines(filename)
        if not lines:
            continue
        header = [name.strip() for name in lines[0].lstrip('#').split(',')]
        highwater_column = _find_column(header, f'VSZ_{column}_N_', filename)
        usage_column = _find_column(header, f'RSS_{column}_N_', filename)
        for line in lines[1:]:
            values = line.split(',')
            if len(values) < len(header):
                continue
            ymd, _, fraction = values[0].strip().partition('.')
            seconds = round(float(f'0.{fraction or 0}') * 86400.0)
            records.append(
                (
                    date_to_days(ymd, seconds),
                    lid,
                    float(values[highwater_column]),
                    float(values[usage_column]),
                )
            )
    return _memory(records)


def read_slurm_jobs(job_ids):
    """
    Read each job's queue wait, run time and largest task memory from
    Slurm's accounting, where ``sacct`` is available

    Parameters
    ----------
    job_ids : list of str
        The batch jobs' IDs

    Returns
    -------
    jobs : dict
        The Job for each ID that Slurm knows, empty if ``sacct`` isn't
        available
    """
    if not job_ids or shutil.which('sacct') is None:
        return {}
    try:
        output = subprocess.run(
            [
                'sacct',
                '--jobs',
                ','.join(job_ids),
                '--noheader',
                '--parsable2',
                '--format',
                'JobID,Submit,Start,End,MaxRSS',
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return {}
    times: dict = {}
    rss: dict = {}
    for line in output.splitlines():
        fields = line.split('|')
        if len(fields) != 5:
            continue
        job_step, submit, start, end, max_rss = fields
        job_id, _, step = job_step.partition('.')
        if not step:
            times[job_id] = (submit, start, end)
        memory = _slurm_memory_mb(max_rss)
        if not np.isnan(memory):
            rss[job_id] = max(rss.get(job_id, 0.0), memory)
    jobs = {}
    for job_id, (submit, start, end) in times.items():
        submitted = _slurm_time(submit)
        started = _slurm_time(start)
        ended = _slurm_time(end)
        if submitted is None or started is None:
            continue
        jobs[job_id] = Job(
            job_id=job_id,
            queue_wait=(started - submitted).total_seconds(),
            elapsed=np.nan
            if ended is None
            else (ended - started).total_seconds(),
            max_rss=rss.get(job_id, np.nan),
        )
    return jobs


def date_to_days(ymd, tod=0):
    """
    Convert one of the driver's dates to days since 0001-01-01 of the
    365-day calendar

    Parameters
    ----------
    ymd : str or int
        The date as ``yyyymmdd``, such as ``00010201``

    tod : str or int, optional
        The seconds into the day

    Returns
    -------
    days : float
        The days since ``0001-01-01_00:00:00``
    """
    ymd = int(ymd)
    year, month, day = ymd // 10000, (ymd // 100) % 100, ymd % 100
    return month_start_days(year, month) + day - 1 + int(tod) / 86400.0


def _read_lines(filename):
    """Read a text file's lines, compressed with gzip or not"""
    opener = gzip.open if filename.endswith('.gz') else open
    with opener(filename, 'rt', errors='replace') as handle:
        return handle.read().splitlines()


def _memory(records):
    """Make a Memory from records of model time, LID, high water and use"""
    return Memory(
        days=np.array([record[0] for record in records]),
        lids=[record[1] for record in records],
        highwater=np.array([record[2] for record in records]),
        usage=np.array([record[3] for record in records]),
    )


def _lid_order(lid):
    """Sort LIDs by the time in them, which is when the segment started"""
    job, _, stamp = lid.partition('.')
    return stamp, int(job)


def _find_column(header, prefix, filename):
    """Find the column of a memory profile that starts with a prefix"""
    for index, name in enumerate(header):
        if name.startswith(prefix):
            return index
    raise ValueError(f'{filename} has no column starting with {prefix}.')


def _slurm_time(value):
    """Parse a time from sacct, or None if the job hasn't reached it"""
    try:
        return datetime.strptime(value, '%Y-%m-%dT%H:%M:%S')
    except ValueError:
        return None


def _slurm_memory_mb(value):
    """Convert a memory from sacct, such as ``1849543K``, to MB"""
    if not value:
        return np.nan
    scales = {'K': 1.0 / 1024.0, 'M': 1.0, 'G': 1024.0, 'T': 1024.0**2}
    if value[-1] in scales:
        return float(value[:-1]) * scales[value[-1]]
    return float(value) / 1024.0**2
