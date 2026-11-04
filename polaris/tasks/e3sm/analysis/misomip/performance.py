import os

import numpy as np
from matplotlib.figure import Figure

from polaris.analysis.product_step import ProductStep
from polaris.e3sm.analysis.performance import (
    find_lid,
    find_timing_files,
    read_node_memory,
    read_root_memory,
    read_segment,
    read_slurm_jobs,
    read_wall_clock_stamps,
)
from polaris.viz.style import mplstyle_context

#: The parts of the ocean's and MALI's run times that their timers give: the
#: label, the component, the timers added and the timers taken away.  A
#: part whose timers a segment lacks is left out, and the rest of each
#: component's run time is its remainder.
RUN_TIME_PARTS = [
    ('ocean: time integration', 'OCN', ['o:time integration'], []),
    (
        'ocean: analysis members',
        'OCN',
        ['o:analysis_compute', 'o:analysis_write'],
        [],
    ),
    (
        'MALI: FEM grid build',
        'GLC',
        ['g:velocity_solver_extrude_3d_grid'],
        [],
    ),
    (
        'MALI: rest of velocity solve',
        'GLC',
        ['g:velocity solve'],
        ['g:velocity_solver_extrude_3d_grid'],
    ),
]

#: The label of the rest of each component's run time
REMAINDERS = {'OCN': 'ocean: other', 'GLC': 'MALI: other'}

#: The order the parts are stacked in
PART_ORDER = [
    'ocean: time integration',
    'ocean: analysis members',
    'ocean: other',
    'MALI: FEM grid build',
    'MALI: rest of velocity solve',
    'MALI: other',
    'coupler and driver',
]

#: The days in a simulated year
DAYS_PER_YEAR = 365.0

#: The width of every figure in inches, the legends' font size and the
#: width of the lines, the same in every figure so they can be shown at one
#: width with the same font sizes
FIG_WIDTH = 10.0
LEGEND_SIZE = 10
LINE_WIDTH = 1.2


class RunPerformance(ProductStep):
    """
    A step that plots an E3SM run's throughput, the share of each model in
    its run time, its cost and its memory over the segments of the run

    Attributes
    ----------
    segment_files : list of tuple of str
        The local names of each segment's timing summary, timer statistics
        (or None) and coupler log

    log_filenames : list of str
        The local names of the coupler's logs, in the order they were
        written

    memory_filenames : list of str
        The local names of the driver's memory profiles
    """

    def __init__(self, component, subdir, case):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory for the step

        case : polaris.e3sm.analysis.case.E3smCase
            The case whose performance is read
        """
        super().__init__(
            component=component,
            name='performance',
            subdir=subdir,
            ntasks=1,
            cpus_per_task=1,
        )
        self.log_filenames = []
        logs_by_lid = {}
        for path in case.find_logs('cpl'):
            if find_lid(path) is None:
                continue
            filename = os.path.join('logs', os.path.basename(path))
            self.add_input_file(filename=filename, target=path)
            self.log_filenames.append(filename)
            logs_by_lid[find_lid(path)] = filename
        self.segment_files = []
        for lid, (summary, stats) in find_timing_files(case.case_dir).items():
            if lid not in logs_by_lid:
                continue
            local_summary = os.path.join('timing', os.path.basename(summary))
            self.add_input_file(filename=local_summary, target=summary)
            local_stats = None
            if stats is not None:
                local_stats = os.path.join('timing', os.path.basename(stats))
                self.add_input_file(filename=local_stats, target=stats)
            self.segment_files.append(
                (local_summary, local_stats, logs_by_lid[lid])
            )
        self.memory_filenames = []
        for path in case.find_logs('memory.3.*'):
            if find_lid(path) is None:
                continue
            filename = os.path.join('logs', os.path.basename(path))
            self.add_input_file(filename=filename, target=path)
            self.memory_filenames.append(filename)
        self.add_output_file(filename='performance.csv')

    def run(self):
        """
        Read and plot the run's performance
        """
        segments = [
            read_segment(summary, stats, log)
            for summary, stats, log in self.segment_files
        ]
        stamps = read_wall_clock_stamps(self.log_filenames)
        root_memory = read_root_memory(self.log_filenames)
        node_memory = None
        if self.memory_filenames:
            node_memory = read_node_memory(self.memory_filenames)
        job_ids = list(
            dict.fromkeys(
                find_lid(filename).split('.')[0]
                for filename in self.log_filenames
            )
        )
        jobs = read_slurm_jobs(job_ids)
        if not jobs:
            self.logger.info(
                "Slurm's accounting isn't available, so queue waits and the "
                'largest task memory are left out.'
            )
        parts = [_run_time_parts(segment) for segment in segments]
        self._write_csv(segments, parts, jobs, root_memory)
        self._log(segments, parts, jobs)
        self._plot_throughput(segments, stamps)
        if segments:
            self._plot_breakdown(segments, parts)
            self._plot_cost(segments, jobs)
        self._plot_memory(root_memory, node_memory, segments, jobs)

    def _write_csv(self, segments, parts, jobs, root_memory):
        """Write one row of each segment's performance"""
        labels = PART_ORDER
        columns = (
            'lid,job_id,start_year,end_year,model_days,sypd,'
            'pe_hours_per_simulated_year,cost_pes,init_s,run_s,final_s,'
            + ','.join(
                f'{_column(label)}_s_per_day,{_column(label)}_share'
                for label in labels
            )
            + ',queue_wait_s,elapsed_s,max_rss_mb,root_highwater_end_mb\n'
        )
        with open('performance.csv', 'w') as csv:
            csv.write(columns)
            for segment, segment_parts in zip(segments, parts, strict=True):
                days = segment.end_day - segment.start_day
                job = jobs.get(segment.job_id)
                highwater = [
                    value
                    for lid, value in zip(
                        root_memory.lids, root_memory.highwater, strict=True
                    )
                    if lid == segment.lid
                ]
                values = [
                    segment.lid,
                    segment.job_id,
                    f'{segment.start_day / DAYS_PER_YEAR:.6g}',
                    f'{segment.end_day / DAYS_PER_YEAR:.6g}',
                    f'{days:g}',
                    f'{segment.throughput:g}',
                    f'{segment.cost:g}',
                    f'{segment.cost_pes}',
                    f'{segment.init_time:g}',
                    f'{segment.run_time:g}',
                    f'{segment.final_time:g}',
                ]
                for label in labels:
                    seconds = segment_parts.get(label, np.nan)
                    values.append(f'{seconds / days:.6g}')
                    values.append(f'{seconds / segment.run_time:.4g}')
                values.extend(
                    [
                        f'{job.queue_wait:g}' if job else '',
                        f'{job.elapsed:g}' if job else '',
                        f'{job.max_rss:.1f}' if job else '',
                        f'{highwater[-1]:.1f}' if highwater else '',
                    ]
                )
                csv.write(','.join(values) + '\n')

    def _log(self, segments, parts, jobs):
        """Log each segment's throughput and the shares of its run time"""
        for segment, segment_parts in zip(segments, parts, strict=True):
            shares = ', '.join(
                f'{label} {100.0 * seconds / segment.run_time:.1f}%'
                for label, seconds in segment_parts.items()
            )
            job = jobs.get(segment.job_id)
            wait = (
                f', queue wait {job.queue_wait / 60.0:.1f} min' if job else ''
            )
            self.logger.info(
                f'{segment.lid}: days {segment.start_day:g} to '
                f'{segment.end_day:g}, {segment.throughput:g} SYPD, '
                f'{segment.cost:g} pe-hours per simulated year, init '
                f'{segment.init_time:g} s, final {segment.final_time:g} s'
                f'{wait}; {shares}'
            )

    def _plot_throughput(self, segments, stamps):
        """Plot each segment's throughput and the coupler's daily rate"""
        with mplstyle_context():
            fig = Figure(figsize=(FIG_WIDTH, 4.0), layout='constrained')
            ax = fig.add_subplot(111)
            daily = 86400.0 / (DAYS_PER_YEAR * stamps.seconds_per_day)
            ax.plot(
                stamps.days / DAYS_PER_YEAR,
                daily,
                '.',
                markersize=3,
                color='0.5',
                label="each model day, from the coupler's wall-clock stamps",
            )
            for index, segment in enumerate(segments):
                ax.plot(
                    [
                        segment.start_day / DAYS_PER_YEAR,
                        segment.end_day / DAYS_PER_YEAR,
                    ],
                    [segment.throughput, segment.throughput],
                    '-',
                    color='C0',
                    linewidth=2.0,
                    label="each segment, from CIME's timing"
                    if index == 0
                    else None,
                )
            ax.set_xlabel('model time (years)')
            ax.set_ylabel('simulated years per day')
            ax.set_title('Throughput')
            ax.set_ylim(bottom=0.0)
            ax.grid(True, alpha=0.3)
            ax.legend(loc='lower right', fontsize=LEGEND_SIZE)
            fig.savefig('throughput.png')
        self.add_product(
            plot='throughput.png',
            group='performance',
            gallery='performance',
            title='Throughput',
        )

    def _plot_breakdown(self, segments, parts):
        """Plot each segment's run time per model day, stacked by part"""
        labels = [
            label
            for label in PART_ORDER
            if any(label in segment_parts for segment_parts in parts)
        ]
        with mplstyle_context():
            fig = Figure(figsize=(FIG_WIDTH, 4.5), layout='constrained')
            ax = fig.add_subplot(111)
            starts = np.array([s.start_day for s in segments]) / DAYS_PER_YEAR
            ends = np.array([s.end_day for s in segments]) / DAYS_PER_YEAR
            days = DAYS_PER_YEAR * (ends - starts)
            bottom = np.zeros(len(segments))
            colors = _part_colors(labels)
            for label in labels:
                values = np.array(
                    [segment_parts.get(label, 0.0) for segment_parts in parts]
                )
                per_day = values / days
                ax.bar(
                    starts,
                    per_day,
                    width=0.95 * (ends - starts),
                    bottom=bottom,
                    align='edge',
                    color=colors[label],
                    label=label,
                )
                bottom += per_day
            ax.set_xlabel('model time (years)')
            ax.set_ylabel('wall-clock seconds per model day')
            ax.set_title('Run time of each segment, by part')
            ax.grid(True, axis='y', alpha=0.3)
            fig.legend(loc='outside right center', fontsize=LEGEND_SIZE)
            fig.savefig('run_time_breakdown.png')
        self.add_product(
            plot='run_time_breakdown.png',
            group='performance',
            gallery='performance',
            title='Run time by part',
        )

    def _plot_cost(self, segments, jobs):
        """Plot each segment's cost, its start-up and finishing times and
        its queue wait"""
        middles = (
            np.array([(s.start_day + s.end_day) / 2.0 for s in segments])
            / DAYS_PER_YEAR
        )
        with mplstyle_context():
            fig = Figure(figsize=(FIG_WIDTH, 6.5), layout='constrained')
            ax = fig.add_subplot(211)
            ax.plot(
                middles, [s.cost for s in segments], 'o-', linewidth=LINE_WIDTH
            )
            pes = sorted({s.cost_pes for s in segments})
            ax.set_ylim(0.0, 1.15 * max(s.cost for s in segments))
            ax.set_ylabel('pe-hours per simulated year')
            ax.set_title(
                f'Cost, on {", ".join(str(p) for p in pes)} processors'
            )
            ax.grid(True, alpha=0.3)
            ax = fig.add_subplot(212, sharex=ax)
            ax.plot(
                middles,
                [s.init_time / 60.0 for s in segments],
                'o-',
                linewidth=LINE_WIDTH,
                label='initialization',
            )
            ax.plot(
                middles,
                [s.final_time / 60.0 for s in segments],
                's-',
                linewidth=LINE_WIDTH,
                label='finalization',
            )
            waits = [
                jobs[s.job_id].queue_wait / 60.0
                if s.job_id in jobs
                else np.nan
                for s in segments
            ]
            if not np.all(np.isnan(waits)):
                ax.plot(
                    middles,
                    waits,
                    '^-',
                    linewidth=LINE_WIDTH,
                    label='queue wait',
                )
            ax.set_xlim(
                segments[0].start_day / DAYS_PER_YEAR,
                segments[-1].end_day / DAYS_PER_YEAR,
            )
            ax.set_xlabel('model time (years)')
            ax.set_ylabel('minutes')
            ax.set_title("Each segment's time outside its run")
            ax.set_ylim(bottom=0.0)
            ax.grid(True, alpha=0.3)
            ax.legend(loc='best', fontsize=LEGEND_SIZE)
            fig.savefig('cost.png')
        self.add_product(
            plot='cost.png',
            group='performance',
            gallery='performance',
            title='Cost and time outside the run',
        )

    def _plot_memory(self, root_memory, node_memory, segments, jobs):
        """Plot the memory of the coupler's root task and its node over
        model time, each segment its own line"""
        if len(root_memory.days) == 0:
            self.logger.info('The coupler logs have no memory records.')
            return
        panels = 1 if node_memory is None else 2
        with mplstyle_context():
            fig = Figure(
                figsize=(FIG_WIDTH, 3.6 * panels), layout='constrained'
            )
            ax = fig.add_subplot(panels, 1, 1)
            _plot_by_segment(ax, root_memory, scale=1.0)
            peaks = [
                (
                    (s.start_day + s.end_day) / (2.0 * DAYS_PER_YEAR),
                    jobs[s.job_id].max_rss,
                )
                for s in segments
                if s.job_id in jobs and not np.isnan(jobs[s.job_id].max_rss)
            ]
            if peaks:
                x, y = zip(*peaks, strict=True)
                ax.plot(
                    x,
                    y,
                    'kx',
                    label="largest task's peak, sampled by Slurm",
                )
            ax.set_ylabel('MB')
            ax.set_title("Memory of the coupler's root task")
            ax.grid(True, alpha=0.3)
            ax.legend(loc='lower right', fontsize=LEGEND_SIZE)
            if node_memory is not None:
                ax = fig.add_subplot(panels, 1, 2, sharex=ax)
                _plot_by_segment(ax, node_memory, scale=1.0 / 1024.0)
                ax.set_ylabel('GB')
                ax.set_title(
                    "Memory of the root task's node, summed over its tasks"
                )
                ax.grid(True, alpha=0.3)
                ax.legend(loc='lower right', fontsize=LEGEND_SIZE)
            ax.set_xlabel('model time (years)')
            fig.savefig('memory.png')
        self.add_product(
            plot='memory.png',
            group='performance',
            gallery='performance',
            title='Memory',
        )


def _run_time_parts(segment):
    """Split a segment's run time into the parts its timers allow, the rest
    of each component's run time and the rest of the total, the coupler's
    and the driver's"""
    times = segment.component_times
    parts = {}
    for label, component, added, taken in RUN_TIME_PARTS:
        if component not in times:
            continue
        if any(name not in segment.timers for name in added + taken):
            continue
        parts[label] = sum(segment.timers[name] for name in added) - sum(
            segment.timers[name] for name in taken
        )
    for component, label in REMAINDERS.items():
        if component not in times:
            continue
        included = sum(
            parts[part]
            for part, part_component, _, _ in RUN_TIME_PARTS
            if part_component == component and part in parts
        )
        parts[label] = times[component] - included
    # the coupler's communication overlaps the models' run times, so the
    # coupler's share is the rest of the total
    parts['coupler and driver'] = segment.run_time - sum(
        times.get(name, 0.0) for name in REMAINDERS
    )
    return {label: parts[label] for label in PART_ORDER if label in parts}


def _plot_by_segment(ax, memory, scale):
    """Plot a memory's high water and use, each segment a line"""
    lids = list(dict.fromkeys(memory.lids))
    for index, lid in enumerate(lids):
        mask = np.array([each == lid for each in memory.lids])
        years = memory.days[mask] / DAYS_PER_YEAR
        ax.plot(
            years,
            scale * memory.highwater[mask],
            '-',
            color='C0',
            linewidth=LINE_WIDTH,
            label='high water' if index == 0 else None,
        )
        ax.plot(
            years,
            scale * memory.usage[mask],
            ':',
            color='C1',
            linewidth=LINE_WIDTH,
            label='in use' if index == 0 else None,
        )


def _part_colors(labels):
    """Colors for the parts: blues for the ocean, reds for MALI"""
    blues = ['#08519c', '#4292c6', '#9ecae1']
    reds = ['#a50f15', '#ef3b2c', '#fc9272']
    colors: dict[str, str] = {}
    for label in labels:
        if label.startswith('ocean'):
            colors[label] = blues[
                sum(each.startswith('ocean') for each in colors)
            ]
        elif label.startswith('MALI'):
            colors[label] = reds[
                sum(each.startswith('MALI') for each in colors)
            ]
        else:
            colors[label] = '#41ab5d'
    return colors


def _column(label):
    """A CSV column's stem from a part's label"""
    return label.replace(': ', '_').replace(' ', '_').replace('-', '_').lower()
