import dataclasses
import datetime
import os
import shutil
from typing import Optional

from polaris.mpas.time import duration_to_seconds
from polaris.tasks.ocean.realistic_global.forward import (
    Forward,
    ForwardStage,
    InitialCondition,
)

#: The package holding this task's yaml overrides
PACKAGE = 'polaris.tasks.ocean.realistic_global.restart'

#: The history the full run writes up to the restart time, which the restart
#: run appends to
BEFORE_RESTART_FILENAME = 'output_before_restart.nc'


class RestartStep(Forward):
    """
    One forward run of the realistic global restart task, shaped like CIME's
    ERS test: the full run, or the restart run that continues from it.

    The full run covers the whole period and writes a restart at
    ``restart_time``, along with its history up to that time in a file of its
    own.  The restart run continues from that restart to the end of the period,
    appending its history to a copy of that file.  Each step writes its
    restarts into a directory of its own under a ``restarts`` directory shared
    by the whole task.

    The run itself is a realistic_global forward run like any other, built
    from the ``[realistic_global_forward]`` config options.  Only the run
    duration, the output interval and the restart are the task's own, and this
    task's ``full_run.yaml`` or ``restart_run.yaml`` adds Omega's start type,
    start time and restart and history streams on top.

    Attributes
    ----------
    run_duration : str
        How long this step runs, as an MPAS-style duration string

    output_interval : str
        The interval between history frames

    restart_time : str
        How far into the period the full run writes the restart the restart
        run continues from, as an MPAS-style duration string

    restart_from : RestartStep or None
        The full run this step continues from, or ``None`` for the full run
    """

    def __init__(
        self,
        component,
        name: str,
        subdir: str,
        init_condition: InitialCondition,
        run_duration: str,
        output_interval: str,
        restart_time: str,
        restart_from: Optional['RestartStep'] = None,
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

        init_condition : polaris.tasks.ocean.realistic_global.forward.InitialCondition
            The source of the model input files

        run_duration : str
            How long this step runs, as an MPAS-style duration string

        output_interval : str
            The interval between history frames

        restart_time : str
            How far into the period the full run writes the restart the
            restart run continues from

        restart_from : RestartStep, optional
            The full run this step continues from.  When given, this step
            reads that run's restart at ``restart_time`` and appends to its
            history up to that time.
        """  # noqa: E501
        super().__init__(
            component=component,
            init_condition=init_condition,
            name=name,
            subdir=subdir,
        )

        self.run_duration = run_duration
        self.output_interval = output_interval
        self.restart_time = restart_time
        self.restart_from = restart_from

        if restart_from is not None:
            # under a name of its own, so that the copy made in
            # runtime_setup() writes to output.nc rather than through a
            # symlink into the full run's work directory
            self.add_input_file(
                filename='previous_output.nc',
                work_dir_target=f'{restart_from.path}/'
                f'{BEFORE_RESTART_FILENAME}',
            )

    def setup(self):
        """
        Reject any model but Omega, declare the restart, then set up the
        forward run
        """
        model = self.config.get('ocean', 'model')
        if model != 'omega':
            raise ValueError(
                f'The realistic_global restart task supports only Omega, not '
                f'{model!r}.  It is a regression test for the way Omega '
                f'writes its history time axis across a restart (Omega '
                f'#482), and MPAS-Ocean stamps its output with xtime rather '
                f'than an elapsed time measured from the clock start, so the '
                f'failure it looks for cannot arise there.'
            )

        self._add_restart_files()
        super().setup()

    def dynamic_model_config(self, at_setup):
        """
        Build this step's stage from config with the task's run duration and
        output interval, then add this task's overrides for the full run or
        the restart run on top of the shared forward yaml, which
        ``Forward.dynamic_model_config()`` adds first

        Parameters
        ----------
        at_setup : bool
            Whether this is being run during setup of the step, as opposed to
            at run time.
        """
        # rebuilt every time, as Forward does when it has no stage, so that a
        # user's config changes after setup still take effect
        stage = ForwardStage.from_config(self.config, name=self.name)
        self.stage = dataclasses.replace(
            stage,
            run_duration=self.run_duration,
            output_interval=self.output_interval,
            restart_interval=self.run_duration,
        )

        super().dynamic_model_config(at_setup=at_setup)

        start_time = self.stage.start_time
        restart_seconds = duration_to_seconds(self.restart_time)
        if self.restart_from is None:
            output_seconds = duration_to_seconds(self.output_interval)
            # after the frame at the restart time and before the next one
            end_seconds = restart_seconds + 0.5 * output_seconds
            self.add_yaml_file(
                package=PACKAGE,
                yaml='full_run.yaml',
                template_replacements=dict(
                    sim_start_time=start_time,
                    restart_dir=self.restart_target(self.name),
                    restart_freq=str(int(round(restart_seconds))),
                    output_freq=str(int(round(output_seconds))),
                    before_restart_end=_time_string(start_time, end_seconds),
                ),
            )
        else:
            self.add_yaml_file(
                package=PACKAGE,
                yaml='restart_run.yaml',
                template_replacements=dict(
                    sim_start_time=start_time,
                    restart_dir=self.restart_target(self.name),
                    restart_read_file=self.restart_file(),
                ),
            )

    def runtime_setup(self):
        """
        Make this step's restart directory, and seed the restart run's history
        file with the full run's history up to the restart
        """
        super().runtime_setup()

        restart_dir = os.path.normpath(
            os.path.join(self.work_dir, self.restart_target(self.name))
        )
        os.makedirs(restart_dir, exist_ok=True)

        if self.restart_from is None:
            return

        # Reproduce what a continuing run finds on disk: a history file that
        # already holds the earlier frames and has to be appended to.  This is
        # copied rather than symlinked so that appending to it cannot reach
        # back into the full run's work directory.
        shutil.copy(
            os.path.join(self.work_dir, 'previous_output.nc'),
            os.path.join(self.work_dir, 'output.nc'),
        )

    def restart_target(self, step_name):
        """
        The path, relative to this step's work directory, of the directory
        the step ``step_name`` writes its restarts into.  Each step gets one
        of its own, so that the restart run cannot replace a restart the full
        run wrote.
        """
        return f'../restarts/{step_name}'

    def restart_file(self):
        """
        The full run's restart at the restart time, relative to this step's
        work directory, named the way Omega names it
        """
        full_run = (
            self.name
            if self.restart_from is None
            else (self.restart_from.name)
        )
        stage = ForwardStage.from_config(self.config, name=self.name)
        stamp = _time_string(
            stage.start_time,
            duration_to_seconds(self.restart_time),
            time_separator='.',
        )
        return f'{self.restart_target(full_run)}/ocn.restart.{stamp}.nc'

    def _add_restart_files(self):
        """
        Declare the restart to Polaris, so that a restart run whose full run
        wrote no restart, or no history up to it, fails before the model
        launches
        """
        if self.restart_from is None:
            self.add_output_file(filename=self.restart_file())
            self.add_output_file(filename=BEFORE_RESTART_FILENAME)
        else:
            self.add_input_file(filename=self.restart_file())


def _time_string(start_time, seconds, time_separator=':'):
    """
    The time ``seconds`` after ``start_time``, an MPAS-style time string
    (``YYYY-MM-DD_hh:mm:ss``), in the same format, with ``time_separator``
    between the hours, minutes and seconds
    """
    start = datetime.datetime.strptime(start_time, '%Y-%m-%d_%H:%M:%S')
    time = start + datetime.timedelta(seconds=seconds)
    sep = time_separator
    return (
        f'{time.year:04d}-{time.month:02d}-{time.day:02d}_'
        f'{time.hour:02d}{sep}{time.minute:02d}{sep}{time.second:02d}'
    )
