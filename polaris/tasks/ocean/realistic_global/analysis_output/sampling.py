import dataclasses
from typing import List, Optional

from polaris import Task
from polaris.config import PolarisConfigParser
from polaris.mpas.time import get_time_interval_string
from polaris.tasks.ocean.realistic_global.analysis_output.sampling_analysis import (  # noqa: E501
    SamplingAnalysis,
)
from polaris.tasks.ocean.realistic_global.forward import (
    Forward,
    ForwardStage,
    InitialCondition,
)
from polaris.tasks.ocean.realistic_global.mesh_configs import (
    add_realistic_global_mesh_config,
)

#: The package holding this task's yaml and config files
PACKAGE = 'polaris.tasks.ocean.realistic_global.analysis_output'

#: The averaging period in days, which every sampling interval has to divide
PERIOD_DAYS = 1

#: The averaging period as Omega spells it
REDUCTION_PERIOD = '1Day'

#: The number of averaging periods the runs cover
NUM_PERIODS = 2

#: How long each run lasts
RUN_DURATION = f'{NUM_PERIODS * PERIOD_DAYS:04d}_00:00:00'

#: The number of time steps between samples in each sampled run, each
#: doubling the last.  The reference run samples every time step.
SAMPLING_STEPS = [2, 4, 8, 16]

#: The date the run starts on, from ``start_time`` in
#: ``[realistic_global_forward]``, which the names of the time-mean files
#: count from
START_DAY = 1


def get_sampling_mean_filenames() -> List[str]:
    """
    Get the names of the time-mean files each forward step writes, one for
    each averaging period, named for the instant the period ends

    Returns
    -------
    filenames : list of str
        The file names
    """
    end_days = [PERIOD_DAYS * period for period in range(1, NUM_PERIODS + 1)]
    return [
        f'means_{REDUCTION_PERIOD}TimeStats.0001-01-{START_DAY + day:02d}.nc'
        for day in end_days
    ]


class SamplingConvergence(Task):
    """
    A task that checks that Omega's time means converge at first order as
    the interval at which they sample the model shrinks

    A ``reference`` run averages every time step.  Each ``sampled_<n>_steps``
    run averages every ``n`` time steps, and the run with the coarsest
    sampling also writes a history snapshot at each sample.  ``analysis``
    then fits the order of convergence of each field's sampled means to the
    reference means, and checks that the coarsest run's means are the means
    of its snapshots.

    This tests the ``SamplingInterval`` of Omega's temporal reductions
    (E3SM-Project/Omega#611).  The runs use RK4, so that a few time steps
    are short compared with the inertial period.
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
            f'spherical/realistic_global/{mesh_name}/analysis_output/'
            f'sampling_convergence'
        )
        super().__init__(
            component=component,
            name='analysis_output_sampling_convergence',
            subdir=subdir,
        )

        # the forward-run options, then this family's defaults, then the
        # per-mesh ones, then RK4 and this task's own options, so that each
        # layer overrides the one before
        config_filename = 'sampling_convergence.cfg'
        config_path = f'{component.name}/{subdir}/{config_filename}'
        config = PolarisConfigParser(filepath=config_path)
        config.add_from_package(
            'polaris.tasks.ocean.realistic_global.forward',
            'forward.cfg',
        )
        config.add_from_package(PACKAGE, 'analysis_output.cfg')
        add_realistic_global_mesh_config(config=config, mesh_name=mesh_name)
        config.add_from_package(
            'polaris.tasks.ocean.realistic_global.forward', 'rk4.cfg'
        )
        config.add_from_package(PACKAGE, config_filename)
        self.set_shared_config(config, link=config_filename)

        run_names = []
        for sampling_steps in [None] + SAMPLING_STEPS:
            step = SampledForward(
                component=component,
                init_condition=init_condition,
                indir=subdir,
                sampling_steps=sampling_steps,
                write_snapshots=sampling_steps == SAMPLING_STEPS[-1],
            )
            step.set_shared_config(config, link=config_filename)
            self.add_step(step)
            run_names.append(step.name)

        analysis = SamplingAnalysis(
            component=component,
            indir=subdir,
            run_names=run_names,
            sampling_steps=SAMPLING_STEPS,
            mean_filenames=get_sampling_mean_filenames(),
            reduction_period=REDUCTION_PERIOD,
            period_seconds=PERIOD_DAYS * 86400.0,
            min_res=init_condition.min_res,
        )
        analysis.set_shared_config(config, link=config_filename)
        self.add_step(analysis)


class SampledForward(Forward):
    """
    A forward run of the sampling_convergence task, averaging at one
    sampling interval

    Attributes
    ----------
    sampling_steps : int or None
        The number of time steps between samples, or ``None`` to sample every
        time step

    write_snapshots : bool
        Whether the run writes a history snapshot at each sample
    """

    def __init__(
        self,
        component,
        init_condition: InitialCondition,
        indir: str,
        sampling_steps: Optional[int],
        write_snapshots: bool,
    ):
        """
        Create the step

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this step belongs to

        init_condition : InitialCondition
            The source of the model input files

        indir : str
            The directory the step is in, to which its name is appended

        sampling_steps : int or None
            The number of time steps between samples, or ``None`` to sample
            every time step

        write_snapshots : bool
            Whether the run writes a history snapshot at each sample
        """
        if sampling_steps is None:
            name = 'reference'
        else:
            name = f'sampled_{sampling_steps}_steps'
        super().__init__(
            component=component,
            init_condition=init_condition,
            name=name,
            indir=indir,
            output_filenames=['output.nc'] + get_sampling_mean_filenames(),
        )
        self.sampling_steps = sampling_steps
        self.write_snapshots = write_snapshots

    def setup(self):
        """
        Raise unless the model is Omega, then set up the step
        """
        if self.config.get('ocean', 'model') != 'omega':
            raise ValueError(
                'The analysis_output sampling_convergence task supports only '
                'Omega, since it tests the sampling of Omega analysis output.'
            )
        super().setup()

    def dynamic_model_config(self, at_setup):
        """
        Build this step's stage from config with the task's run duration, and
        add the analysis output over the forward step's model config

        Parameters
        ----------
        at_setup : bool
            Whether this is being run during setup of the step, as opposed to
            at run time.
        """
        config = self.config
        if self.write_snapshots:
            assert self.sampling_steps is not None
            dt = ForwardStage.from_config(config).time_step_seconds(
                model=config.get('ocean', 'model'),
                min_res=self.init_condition.min_res,
            )
            output_interval = get_time_interval_string(
                seconds=self.sampling_steps * dt
            )
        else:
            output_interval = RUN_DURATION

        # rebuilt every time, as Forward does when it has no stage, so that a
        # user's config changes after setup still take effect
        stage = ForwardStage.from_config(config, name=self.name)
        self.stage = dataclasses.replace(
            stage,
            run_duration=RUN_DURATION,
            output_interval=output_interval,
            restart_interval=RUN_DURATION,
        )

        super().dynamic_model_config(at_setup=at_setup)

        if self.sampling_steps is None:
            sampling_interval = 'dt'
        else:
            sampling_interval = f'{self.sampling_steps}steps'
        self.add_yaml_file(
            PACKAGE,
            'sampling_analysis.yaml',
            template_replacements=dict(
                fields=config.getlist('analysis_output_sampling', 'fields'),
                period=REDUCTION_PERIOD,
                sampling_interval=sampling_interval,
                file_freq_days=PERIOD_DAYS,
            ),
        )
