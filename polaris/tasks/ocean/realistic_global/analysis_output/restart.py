from typing import List, Optional

from polaris import Task
from polaris.config import PolarisConfigParser
from polaris.tasks.ocean.realistic_global.analysis_output.restart_validate import (  # noqa: E501
    AnalysisRestartValidate,
)
from polaris.tasks.ocean.realistic_global.forward import InitialCondition
from polaris.tasks.ocean.realistic_global.mesh_configs import (
    add_realistic_global_mesh_config,
)
from polaris.tasks.ocean.realistic_global.restart import RestartStep

#: The package holding this task's yaml and config files
PACKAGE = 'polaris.tasks.ocean.realistic_global.analysis_output'

#: The averaging period of every analysis group, in days
PERIOD_DAYS = 2

#: The averaging period as Omega spells it
REDUCTION_PERIOD = f'{PERIOD_DAYS}Days'

#: How long the full run lasts, in days: two averaging periods
FULL_RUN_DAYS = 2 * PERIOD_DAYS

#: How far into the full run, in days, it writes the restart the restart run
#: continues from: half an averaging period, so that the restart falls midway
#: through the first one
RESTART_DAYS = PERIOD_DAYS // 2

#: The interval between history frames
OUTPUT_INTERVAL = '0001_00:00:00'

#: The sampling interval of the MOC group: every 16 hours, so that the
#: restart, 24 hours in, falls between two samples
MOC_SAMPLING_INTERVAL = '3perPeriod'

#: The sampling interval of the GlobalStats group: every 6 hours, so that the
#: restart falls on a sample
STATS_SAMPLING_INTERVAL = '6hour'

#: The date the run starts on, from ``start_time`` in
#: ``[realistic_global_forward]``, which the names of the time-mean files
#: count from
START_DAY = 1


def get_analysis_restart_filenames() -> List[str]:
    """
    Get the names of the time-mean files that the full run and the restart
    run both write, relative to a step's work directory

    Omega names a time-mean file for the instant the period ends, so the
    two periods of a run that starts on ``0001-01-01`` are written to files
    dated ``0001-01-03`` and ``0001-01-05``.  The ``GlobalStats`` reductions
    are written to a single file, since the forward step gives that group a
    file name with no time template.

    Returns
    -------
    filenames : list of str
        The file names
    """
    filenames = []
    for end_day in range(PERIOD_DAYS, FULL_RUN_DAYS + 1, PERIOD_DAYS):
        stamp = f'0001-01-{START_DAY + end_day:02d}'
        for prefix in ['means', 'moc']:
            filenames.append(
                f'{prefix}_{REDUCTION_PERIOD}TimeStats.{stamp}.nc'
            )
    filenames.append(f'global_stats_{REDUCTION_PERIOD}TimeStats')
    return filenames


class AnalysisRestart(Task):
    """
    A task that checks that a run continued from a restart midway through an
    averaging period writes the same time means as the uninterrupted run,
    shaped like CIME's ERS test

    A ``full_run`` covers two averaging periods and writes a restart halfway
    through the first.  A ``restart_run`` continues from that restart to the
    end of the second period.  ``validate`` then checks that the restart run
    wrote the same time means as the full run, bit for bit.

    This is the regression test for Omega's checkpointing of the accumulation
    state of its temporal reductions (E3SM-Project/Omega#611).  The steps are
    those of the realistic_global ``restart`` task, with the
    ``MonthlyAverages``, ``MOC`` and ``GlobalStats`` analysis groups averaging
    over the same period; see ``restart_analysis.yaml`` for how each samples.
    """

    def __init__(
        self, component, mesh_name: str, init_condition: InitialCondition
    ):
        """
        Create the task

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this task belongs to

        mesh_name : str
            The name of the mesh (e.g. ``e3sm-qu240``)

        init_condition : InitialCondition
            The source of the model input files, shared by every forward step
        """
        subdir = (
            f'spherical/realistic_global/{mesh_name}/analysis_output/restart'
        )
        super().__init__(
            component=component,
            name='analysis_output_restart',
            subdir=subdir,
        )

        # the forward-run options, then this family's defaults, then the
        # per-mesh ones, so that each layer overrides the one before
        config_filename = 'analysis_output.cfg'
        config_path = f'{component.name}/{subdir}/{config_filename}'
        config = PolarisConfigParser(filepath=config_path)
        config.add_from_package(
            'polaris.tasks.ocean.realistic_global.forward',
            'forward.cfg',
        )
        config.add_from_package(PACKAGE, config_filename)
        add_realistic_global_mesh_config(config=config, mesh_name=mesh_name)
        self.set_shared_config(config, link=config_filename)

        filenames = get_analysis_restart_filenames()

        # the uninterrupted run, which also writes the restart the restart run
        # continues from
        full_run = AnalysisRestartStep(
            component=component,
            name='full_run',
            subdir=f'{subdir}/full_run',
            init_condition=init_condition,
            run_duration=_duration(FULL_RUN_DAYS),
            analysis_filenames=filenames,
        )
        full_run.set_shared_config(config, link=config_filename)
        self.add_step(full_run)

        # every period ends after the restart, so the restart run writes all
        # the time means
        restart_run = AnalysisRestartStep(
            component=component,
            name='restart_run',
            subdir=f'{subdir}/restart_run',
            init_condition=init_condition,
            run_duration=_duration(FULL_RUN_DAYS - RESTART_DAYS),
            analysis_filenames=filenames,
            restart_from=full_run,
        )
        restart_run.set_shared_config(config, link=config_filename)
        self.add_step(restart_run)

        validate = AnalysisRestartValidate(
            component=component,
            full_run_subdir='full_run',
            restart_subdir='restart_run',
            analysis_filenames=filenames,
            indir=subdir,
        )
        validate.set_shared_config(config, link=config_filename)
        self.add_step(validate)


class AnalysisRestartStep(RestartStep):
    """
    One forward run of the analysis_output restart task: the full run, or the
    restart run that continues from it, with the task's analysis output on

    Attributes
    ----------
    analysis_filenames : list of str
        The time-mean files the step writes, declared as outputs
    """

    def __init__(
        self,
        component,
        name: str,
        subdir: str,
        init_condition: InitialCondition,
        run_duration: str,
        analysis_filenames: List[str],
        restart_from: Optional[RestartStep] = None,
    ):
        """
        Create the step

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this step belongs to

        name : str
            The name of the step

        subdir : str
            The subdirectory for the step

        init_condition : InitialCondition
            The source of the model input files

        run_duration : str
            How long this step runs, as an MPAS-style duration string

        analysis_filenames : list of str
            The time-mean files the step writes, declared as outputs so that
            a reduction that was not written fails the step

        restart_from : polaris.tasks.ocean.realistic_global.restart.RestartStep, optional
            The full run this step continues from
        """  # noqa: E501
        super().__init__(
            component=component,
            name=name,
            subdir=subdir,
            init_condition=init_condition,
            run_duration=run_duration,
            output_interval=OUTPUT_INTERVAL,
            restart_time=_duration(RESTART_DAYS),
            restart_from=restart_from,
        )
        self.analysis_filenames = analysis_filenames
        for filename in analysis_filenames:
            self.add_output_file(filename=filename)

    def setup(self):
        """
        Raise unless the model is Omega, then set up the step
        """
        if self.config.get('ocean', 'model') != 'omega':
            raise ValueError(
                'The analysis_output restart task supports only Omega, '
                'since it tests the checkpointing of Omega analysis output.'
            )
        super().setup()

    def dynamic_model_config(self, at_setup):
        """
        Add the analysis output over the restart task's model config

        Parameters
        ----------
        at_setup : bool
            Whether this is being run during setup of the step, as opposed to
            at run time.
        """
        super().dynamic_model_config(at_setup=at_setup)
        self.add_yaml_file(
            PACKAGE,
            'restart_analysis.yaml',
            template_replacements=dict(
                period=REDUCTION_PERIOD,
                file_freq_days=PERIOD_DAYS,
                moc_num_bins=self.config.getint(
                    'analysis_output', 'moc_num_bins'
                ),
                moc_sampling_interval=MOC_SAMPLING_INTERVAL,
                stats_sampling_interval=STATS_SAMPLING_INTERVAL,
            ),
        )


def _duration(days: int) -> str:
    """A whole number of days as an MPAS-style duration string"""
    return f'{days:04d}_00:00:00'
