from polaris import Task as Task
from polaris.config import PolarisConfigParser as PolarisConfigParser
from polaris.tasks.ocean.realistic_global.forward import (
    InitialCondition as InitialCondition,
)
from polaris.tasks.ocean.realistic_global.mesh_configs import (
    add_realistic_global_mesh_config,
)
from polaris.tasks.ocean.realistic_global.restart.restart_step import (
    RestartStep as RestartStep,
)
from polaris.tasks.ocean.realistic_global.restart.validate import (
    Validate as Validate,
)

#: How long the full run covers.  The period is short on purpose: this task is
#: about how the model restarts and writes its history across a restart, not
#: about the circulation, and it is meant to be cheap enough for the
#: pull-request suite.
FULL_DURATION = '0000_04:00:00'

#: How far into the period the full run writes the restart the restart run
#: continues from, as the base run of CIME's ERS test does partway through
RESTART_TIME = '0000_02:00:00'

#: How long the restart run covers: the rest of the period
RESTART_DURATION = '0000_02:00:00'

#: How often a history frame is written.  Two frames on each side of the
#: restart, so that a restart run that clobbered rather than appended would be
#: obvious.
OUTPUT_INTERVAL = '0000_01:00:00'


class Restart(Task):
    """
    A task that checks that a run continued from a restart reproduces the
    uninterrupted run, history included, shaped like CIME's ERS test.

    A ``full_run`` covers the whole period and writes a restart partway
    through, along with its history up to that restart in a file of its own.
    A ``restart_run`` continues from that restart to the end of the period,
    appending its frames to a copy of that history.  A ``validate`` step then
    checks that the two histories hold the same frames at the same times and
    the same state.

    Appending is also a regression test for Omega #482, where a continuing run
    measured its history time axis from its own start rather than the
    simulation's, so its first frame collided with the first frame already in
    the file and silently replaced the earlier frames.
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
        subdir = f'spherical/realistic_global/{mesh_name}/restart'
        super().__init__(component=component, name='restart', subdir=subdir)

        # the forward-run options, then the per-mesh ones, then this task's,
        # so that each layer overrides the one before
        config_filename = 'restart.cfg'
        config_path = f'{component.name}/{subdir}/{config_filename}'
        config = PolarisConfigParser(filepath=config_path)
        config.add_from_package(
            'polaris.tasks.ocean.realistic_global.forward',
            'forward.cfg',
        )
        add_realistic_global_mesh_config(config=config, mesh_name=mesh_name)
        config.add_from_package(
            'polaris.tasks.ocean.realistic_global.restart',
            config_filename,
        )
        self.set_shared_config(config, link=config_filename)

        # the uninterrupted run, which also writes the restart and the history
        # up to it that the restart run starts from
        full_run = RestartStep(
            component=component,
            name='full_run',
            subdir=f'{subdir}/full_run',
            init_condition=init_condition,
            run_duration=FULL_DURATION,
            output_interval=OUTPUT_INTERVAL,
            restart_time=RESTART_TIME,
        )
        full_run.set_shared_config(config, link=config_filename)
        self.add_step(full_run)

        restart_run = RestartStep(
            component=component,
            name='restart_run',
            subdir=f'{subdir}/restart_run',
            init_condition=init_condition,
            run_duration=RESTART_DURATION,
            output_interval=OUTPUT_INTERVAL,
            restart_time=RESTART_TIME,
            restart_from=full_run,
        )
        restart_run.set_shared_config(config, link=config_filename)
        self.add_step(restart_run)

        validate = Validate(
            component=component,
            full_run_subdir='full_run',
            restart_subdir='restart_run',
            indir=subdir,
        )
        validate.set_shared_config(config, link=config_filename)
        self.add_step(validate)
