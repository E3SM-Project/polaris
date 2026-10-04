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

#: How long each segment of the restart chain runs.  The full run covers two
#: of these.  The period is short on purpose: this task is about how the model
#: writes its history across a restart, not about the circulation, and it is
#: meant to be cheap enough for the pull-request suite.
SEGMENT_DURATION = '0000_02:00:00'

#: The full run, which the restart chain is compared against
FULL_DURATION = '0000_04:00:00'

#: How often a history frame is written.  Two frames per segment, so that a
#: segment that clobbered rather than appended would be obvious.
OUTPUT_INTERVAL = '0000_01:00:00'


class Restart(Task):
    """
    A task that checks that splitting a run across a restart leaves the
    history output alone.

    A ``full_run`` covers the whole period in one go.  Two further steps cover
    the same period in two segments, the second continuing from the restart
    the first wrote and appending its frames to the history the first left
    behind.  A ``validate`` step then checks that the two histories hold the
    same frames at the same times and the same state.

    This is a regression test for Omega #482, where the continuing segment
    measured its history time axis from its own start rather than the
    simulation's, so its first frame collided with the first frame already in
    the file and silently replaced the earlier half of the run.
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
            The name of the mesh (e.g. ``QU.240km``)

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
            'realistic_global_forward.cfg',
        )
        add_realistic_global_mesh_config(config=config, mesh_name=mesh_name)
        config.add_from_package(
            'polaris.tasks.ocean.realistic_global.restart',
            config_filename,
        )
        self.set_shared_config(config, link=config_filename)

        # the uninterrupted run the restart chain is measured against.  It is
        # a RestartStep too, so that it runs exactly the model the chain does,
        # but it starts up rather than continuing and writes its restart into
        # a directory of its own, so that its restart cannot be mistaken for
        # the chain's
        full_run = RestartStep(
            component=component,
            name='full_run',
            subdir=f'{subdir}/full_run',
            init_condition=init_condition,
            run_duration=FULL_DURATION,
            output_interval=OUTPUT_INTERVAL,
        )
        full_run.set_shared_config(config, link=config_filename)
        self.add_step(full_run)

        previous_step = None
        for name in ['first_segment', 'second_segment']:
            step = RestartStep(
                component=component,
                name=name,
                subdir=f'{subdir}/{name}',
                init_condition=init_condition,
                run_duration=SEGMENT_DURATION,
                output_interval=OUTPUT_INTERVAL,
                previous_step=previous_step,
            )
            step.set_shared_config(config, link=config_filename)
            self.add_step(step)
            previous_step = step

        validate = Validate(
            component=component,
            full_run_subdir='full_run',
            restart_subdir='second_segment',
            indir=subdir,
        )
        validate.set_shared_config(config, link=config_filename)
        self.add_step(validate)
