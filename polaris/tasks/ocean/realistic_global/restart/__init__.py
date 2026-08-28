from polaris import Task as Task
from polaris.config import PolarisConfigParser as PolarisConfigParser
from polaris.tasks.ocean.realistic_global.forward import Forward as Forward
from polaris.tasks.ocean.realistic_global.restart.restart_step import (
    RestartStep as RestartStep,
)
from polaris.tasks.ocean.realistic_global.restart.validate import (
    Validate as Validate,
)

#: The start of the simulation, shared by every step so that the history time
#: axis of the restart chain lines up with that of the full run
SIM_START_TIME = '0001-01-01_00:00:00'

#: How long each segment of the restart chain runs.  The full run covers two
#: of these.  The period is short on purpose: this task is about how the model
#: writes its history across a restart, not about the circulation, and it is
#: meant to be cheap enough for the pull-request suite.
SEGMENT_DURATION = '0000_01:00:00'

#: The full run, which the restart chain is compared against
FULL_DURATION = '0000_02:00:00'

#: How often a history frame is written.  Two frames per segment, so that a
#: segment that clobbered rather than appended would be obvious.
OUTPUT_INTERVAL = '0000_00:30:00'
OUTPUT_FREQ = '30'
OUTPUT_FREQ_UNITS = 'minutes'

#: Per-mesh time step
DT = {'QU.240km': '00:10:00'}


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
        self, component, subdir, mesh_name, mpaso_id, omega_id, ncells
    ):
        """
        Create the task

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this task belongs to

        subdir : str
            The subdirectory for the task, to which ``restart`` will be
            appended

        mesh_name : str
            The name of the mesh (e.g. ``QU.240km``)

        mpaso_id : int
            The ID of the MPAS-Ocean initial condition in the Polaris input
            database

        omega_id : int
            The ID of the Omega initial condition in the Polaris input
            database

        ncells : int
            The approximate number of cells in the mesh, used to constrain
            resources
        """
        subdir = f'{subdir}/restart'
        super().__init__(component=component, name='restart', subdir=subdir)

        config_filename = 'restart.cfg'
        config_path = f'{component.name}/{subdir}/{config_filename}'
        config = PolarisConfigParser(filepath=config_path)
        config.add_from_package(
            'polaris.tasks.ocean.realistic_global',
            'realistic_global.cfg',
        )
        config.add_from_package(
            'polaris.tasks.ocean.realistic_global.restart',
            config_filename,
        )
        self.set_shared_config(config, link=config_filename)

        shared = dict(
            time_integrator='RungeKutta4',
            dt=DT[mesh_name],
            output_interval=OUTPUT_INTERVAL,
            output_freq=OUTPUT_FREQ,
            output_freq_units=OUTPUT_FREQ_UNITS,
            sim_start_time=SIM_START_TIME,
        )

        mesh_args = dict(
            mesh_name=mesh_name,
            mpaso_id=mpaso_id,
            omega_id=omega_id,
            ncells=ncells,
        )

        # the uninterrupted run the restart chain is measured against; it
        # keeps its own restart directory rather than the one the chain
        # shares, so that its restart cannot be mistaken for the chain's
        full_run = Forward(
            component=component,
            package='polaris.tasks.ocean.realistic_global',
            name='full_run',
            subdir=f'{subdir}/full_run',
            replacements=dict(shared, run_duration=FULL_DURATION),
            **mesh_args,
        )
        full_run.set_shared_config(config, link=config_filename)
        self.add_step(full_run)

        previous_step = None
        for name, start_type in [
            ('first_segment', 'StartUp'),
            ('second_segment', 'Continue'),
        ]:
            step = RestartStep(
                component=component,
                name=name,
                subdir=f'{subdir}/{name}',
                replacements=dict(
                    shared,
                    run_duration=SEGMENT_DURATION,
                    start_type=start_type,
                ),
                previous_step=previous_step,
                **mesh_args,
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
