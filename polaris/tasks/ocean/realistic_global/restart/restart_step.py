import dataclasses
import os
import shutil

from polaris.tasks.ocean.realistic_global.forward import (
    Forward,
    ForwardStage,
)

#: The package holding this task's yaml overrides
PACKAGE = 'polaris.tasks.ocean.realistic_global.restart'


class RestartStep(Forward):
    """
    One forward run of the realistic global restart task: the full run, or
    one segment of the restart chain.

    The chain is two segments that between them cover the same period as the
    task's ``full_run``.  Each step writes its restart into a directory of its
    own under a ``restarts`` directory shared by the whole task, and the
    continuing segment reads its predecessor's and appends its history to the
    frames the first segment already wrote.

    The run itself is a realistic_global forward run like any other, built
    from the ``[realistic_global_forward]`` config options.  Only the run
    duration and output interval are the task's own, and this task's
    ``forward.yaml`` adds Omega's start type, start time and restart streams on
    top.

    Attributes
    ----------
    run_duration : str
        How long this step runs, as an MPAS-style duration string

    output_interval : str
        The interval between history frames

    previous_step : polaris.Step or None
        The segment this one continues from, or ``None`` for a step that
        starts from the initial condition.
    """

    def __init__(
        self,
        component,
        name,
        subdir,
        init_condition,
        run_duration,
        output_interval,
        previous_step=None,
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

        previous_step : polaris.Step, optional
            The segment this one continues from.  When given, this step reads
            that segment's restart and appends to its history file.
        """  # noqa: E501
        super().__init__(
            component=component,
            init_condition=init_condition,
            name=name,
            subdir=subdir,
        )

        self.run_duration = run_duration
        self.output_interval = output_interval
        self.previous_step = previous_step

        if previous_step is not None:
            # under a name of its own, so that the copy made in
            # runtime_setup() writes to output.nc rather than through a
            # symlink into the previous segment's work directory
            self.add_input_file(
                filename='previous_output.nc',
                work_dir_target=f'{previous_step.path}/output.nc',
            )

    def setup(self):
        """
        Reject any model but Omega, then set up the forward run
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

        super().setup()

    def dynamic_model_config(self, at_setup):
        """
        Build this step's stage from config with the task's run duration and
        output interval, then add this task's overrides on top of the shared
        forward yaml, which ``Forward.dynamic_model_config()`` adds first

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

        start_type = 'StartUp' if self.previous_step is None else 'Continue'
        self.add_yaml_file(
            package=PACKAGE,
            yaml='forward.yaml',
            template_replacements=dict(
                start_type=start_type,
                sim_start_time=self.stage.start_time,
                restart_read_dir=self.restart_read_target(),
                restart_write_dir=self.restart_write_target(),
            ),
        )

    def runtime_setup(self):
        """
        Make this step's restart directory, and seed the history file with the
        previous segment's frames when this segment continues from one
        """
        super().runtime_setup()

        os.makedirs(self.restart_write_dir(), exist_ok=True)

        if self.previous_step is None:
            return

        # Reproduce what a continuation run finds on disk: a history file
        # that already holds the earlier frames and has to be appended to.
        # This is copied rather than symlinked so that appending to it cannot
        # reach back into the previous segment's work directory.
        shutil.copy(
            os.path.join(self.work_dir, 'previous_output.nc'),
            os.path.join(self.work_dir, 'output.nc'),
        )

    def restart_write_dir(self):
        """
        The absolute path of the directory this step writes its restart into
        """
        return os.path.normpath(
            os.path.join(self.work_dir, self.restart_write_target())
        )

    def restart_write_target(self):
        """
        The path, relative to the step's work directory, that this step writes
        its restart into.  Each step gets one of its own, so that a segment's
        own restart cannot replace the pointer it read from.
        """
        return f'../restarts/{self.name}'

    def restart_read_target(self):
        """
        The path, relative to the step's work directory, that this step reads
        a restart from.  A step that starts from an initial state never opens
        it, so it is pointed at its own directory.
        """
        if self.previous_step is None:
            return self.restart_write_target()
        return f'../restarts/{self.previous_step.name}'
