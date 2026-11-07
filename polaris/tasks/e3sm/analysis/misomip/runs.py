"""
The runs of each MISOMIP experiment that the config names, and the monthly
means each holds
"""

from typing import NamedTuple

from polaris.e3sm.analysis.calendar import month_start_days
from polaris.e3sm.analysis.runs import (
    E3smRun,
    StandaloneRun,
    month_range_key,
    select_months,
)

#: The pairs of ocean and MALI meshes the experiments run on
MESH_NAMES = ['misomip-o4km-li1km', 'misomip-o2km-li1km']

#: The experiments analyzed
EXPERIMENTS = [
    'ocean0',
    'ocean1',
    'ocean2',
    'ocean3',
    'ocean4',
    'iceocean1r',
    'iceocean1ra',
]

#: The experiments in which MALI evolves, coupled to the ocean
COUPLED_EXPERIMENTS = ['iceocean1r', 'iceocean1ra']

#: The experiments that continue from the end of another, whose initial
#: conditions hold their meshes and MALI's bed
CONTINUES_FROM = {'iceocean1ra': 'iceocean1r'}

#: The kinds of run, each a config option per experiment
RUN_KINDS = {'e3sm': 'e3sm_case', 'standalone': 'standalone'}

#: The ocean's stream of monthly means and of daily global statistics
MONTHLY_STREAM = 'timeSeriesStatsMonthlyOutput'
DAILY_STREAM = 'globalStatsOutput'

#: The ocean's stream of daily means, which a run may write
DAILY_MEANS_STREAM = 'timeSeriesStatsDailyOutput'

#: The ocean's snapshots of layer thickness at each month's start, which with
#: the monthly mean of ``vertAleTransportTop`` give the overturning
#: streamfunction from the volume budget
SNAPSHOT_STREAM = 'layerThicknessSnapshotOutput'


class ConfiguredRun(NamedTuple):
    """
    A run the config names, with the monthly means in the years analyzed

    Attributes
    ----------
    kind : str
        ``e3sm`` or ``standalone``

    path : str
        The case directory or the forward step's work directory

    run : polaris.e3sm.analysis.runs.E3smRun or StandaloneRun
        The run, for its ocean output

    monthly : list of polaris.streams.StreamFile
        The monthly means in the years analyzed

    key : str
        The months they cover, such as ``0001-01_0001-12``

    continues : ConfiguredRun or None
        The run of the same kind that this one continues from, whose initial
        conditions hold the meshes and MALI's bed, or ``None``
    """

    kind: str
    path: str
    run: E3smRun | StandaloneRun
    monthly: list
    key: str
    continues: 'ConfiguredRun | None' = None

    @property
    def initial_run(self):
        """The run whose initial conditions this run's analysis reads"""
        if self.continues is not None:
            return self.continues.initial_run
        return self.run

    @property
    def period(self):
        """The months analyzed, as days since 0001-01-01 from the start of
        the first to the end of the last"""
        first = self.monthly[0]
        last = self.monthly[-1]
        return (
            month_start_days(first.year, first.month),
            month_start_days(last.year, last.month + 1),
        )


def runs_section(mesh_name):
    """
    Get the config section naming the runs on a mesh

    Parameters
    ----------
    mesh_name : str
        The pair of meshes, such as ``misomip-o4km-li1km``

    Returns
    -------
    section : str
        The section
    """
    return f'misomip_analysis_{mesh_name}'


def get_configured_runs(config, mesh_name, experiment):
    """
    Get the runs of an experiment that the config names

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        The config options

    mesh_name : str
        The pair of meshes

    experiment : str
        The experiment, such as ``ocean0``

    Returns
    -------
    runs : dict of str to ConfiguredRun
        The runs, by kind
    """
    section = config[runs_section(mesh_name)]
    analysis = config['misomip_analysis']
    start_year = analysis.getint('start_year')
    end_year = analysis.getint('end_year')
    base_runs = dict()
    if experiment in CONTINUES_FROM:
        base_runs = get_configured_runs(
            config, mesh_name, CONTINUES_FROM[experiment]
        )
    runs = dict()
    for kind, suffix in RUN_KINDS.items():
        path = section.get(f'{experiment}_{suffix}', '').strip()
        if not path:
            continue
        if kind == 'e3sm':
            run: E3smRun | StandaloneRun = E3smRun(path, 'mpaso')
        else:
            run = StandaloneRun(path)
        monthly = select_months(
            run.find_stream_files(MONTHLY_STREAM), start_year, end_year
        )
        continues = None
        if experiment in CONTINUES_FROM:
            base = CONTINUES_FROM[experiment]
            if kind not in base_runs:
                raise ValueError(
                    f'{experiment} continues from {base}, whose initial '
                    f'conditions hold its meshes, so set {base}_{suffix} in '
                    f'[{runs_section(mesh_name)}] too.'
                )
            continues = base_runs[kind]
        runs[kind] = ConfiguredRun(
            kind=kind,
            path=path,
            run=run,
            monthly=monthly,
            key=month_range_key(monthly),
            continues=continues,
        )
    return runs


def get_mean_months(config, experiment):
    """
    Get the number of months at the end of a run that time means cover

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        The config options

    experiment : str
        The experiment

    Returns
    -------
    count : int
        The number of months
    """
    option = f'mean_months_{experiment}'
    if not config.has_option('misomip_analysis', option):
        option = 'mean_months'
    return config.getint('misomip_analysis', option)
