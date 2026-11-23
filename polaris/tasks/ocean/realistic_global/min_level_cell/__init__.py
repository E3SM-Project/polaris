from typing import List

from polaris import Step, Task
from polaris.config import PolarisConfigParser
from polaris.mpas.time import duration_to_seconds
from polaris.tasks.ocean.realistic_global.forward import (
    TIME_INTEGRATORS,
    Forward,
    InitialCondition,
)
from polaris.tasks.ocean.realistic_global.mesh_configs import (
    add_realistic_global_mesh_config,
)
from polaris.tasks.ocean.realistic_global.min_level_cell.add_top_level import (
    AddTopLevel as AddTopLevel,
)
from polaris.tasks.ocean.realistic_global.min_level_cell.add_top_level import (
    TopLevelInitialCondition as TopLevelInitialCondition,
)
from polaris.tasks.ocean.realistic_global.min_level_cell.add_top_level import (
    add_top_level as add_top_level,
)
from polaris.tasks.ocean.realistic_global.min_level_cell.compare import (
    MLD_FILENAME,
)
from polaris.tasks.ocean.realistic_global.min_level_cell.compare import (
    Compare as Compare,
)
from polaris.tasks.ocean.realistic_global.min_level_cell.compare import (
    compare_identical as compare_identical,
)
from polaris.tasks.ocean.realistic_global.min_level_cell.compare import (
    compare_shifted as compare_shifted,
)
from polaris.tasks.ocean.realistic_global.restart import RestartStep


class MinLevelCell(Task):
    """
    A task that checks that an inactive level above every column changes
    nothing: a forward run with ``minLevelCell = 2`` everywhere and
    ``maxLevelCell`` one higher than usual has to be bit-for-bit identical to
    the same run without the added level, one level lower.

    The ``reference`` step is a realistic_global forward run like any other.
    ``add_top_level`` writes a copy of its initial condition with a level of
    zero thickness added above every column, and ``shifted`` runs from that
    copy with the same config.  ``compare`` then checks every field the two
    runs wrote.  Any code that starts a column at level 1 rather than at
    ``minLevelCell`` shows up as a difference, which is what makes this a test
    of the code that handles columns under ice shelves, on a mesh without
    any.

    For Omega, ``shifted`` also writes a restart partway through, and
    ``shifted_restart`` continues from it to the end of the run.  ``compare``
    then also checks that ``shifted_restart`` is identical to ``shifted``, so
    that a restart that loses or misreads ``MinLayerCell`` shows up.  The
    restart is Omega's only, as in the ``restart`` task.

    Attributes
    ----------
    mesh_name : str
        The name of the MPAS mesh

    time_integrator : str
        The variant of the task, one of ``TIME_INTEGRATORS``
    """

    def __init__(
        self,
        component,
        mesh_name: str,
        init_condition: InitialCondition,
        time_integrator: str = 'split_explicit',
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
            The source of the model input files without the added level

        time_integrator : str, optional
            The variant of the task, one of ``TIME_INTEGRATORS``: the default
            split time stepping or RK4.  It is also the name of the task's
            directory.
        """
        if time_integrator not in TIME_INTEGRATORS:
            raise ValueError(
                f'Unexpected time_integrator {time_integrator!r}; expected '
                f'one of {TIME_INTEGRATORS}'
            )
        subdir = (
            f'spherical/realistic_global/{mesh_name}/min_level_cell/'
            f'{time_integrator}'
        )
        super().__init__(
            component=component, name='min_level_cell', subdir=subdir
        )
        self.mesh_name = mesh_name
        self.time_integrator = time_integrator

        # the forward-run options, then the per-mesh ones, then this task's,
        # so that each layer overrides the one before
        config_filename = 'min_level_cell.cfg'
        config_path = f'{component.name}/{subdir}/{config_filename}'
        config = PolarisConfigParser(filepath=config_path)
        config.add_from_package(
            'polaris.tasks.ocean.realistic_global.forward', 'forward.cfg'
        )
        add_realistic_global_mesh_config(config=config, mesh_name=mesh_name)
        if time_integrator == 'rk4':
            config.add_from_package(
                'polaris.tasks.ocean.realistic_global.forward', 'rk4.cfg'
            )
        config.add_from_package(
            'polaris.tasks.ocean.realistic_global.min_level_cell',
            config_filename,
        )
        self.set_shared_config(config, link=config_filename)

        reference = Forward(
            component=component,
            name='reference',
            subdir=f'{subdir}/reference',
            init_condition=init_condition,
            validate_class='state',
        )

        add_top_level = AddTopLevel(
            component=component, indir=subdir, init_condition=init_condition
        )
        self.top_level_init = TopLevelInitialCondition(add_top_level)

        shifted = Forward(
            component=component,
            name='shifted',
            subdir=f'{subdir}/shifted',
            init_condition=self.top_level_init,
            validate_class='state',
        )

        compare = Compare(
            component=component,
            indir=subdir,
            reference_subdir=reference.name,
            shifted_subdir=shifted.name,
        )

        steps: List[Step] = [reference, add_top_level, shifted, compare]
        for step in steps:
            step.set_shared_config(config, link=config_filename)
            self.add_step(step)

    def configure(self):
        """
        Set up the runs and comparisons for the configured model: the
        mixed-layer depths for MPAS-Ocean, and the restart for Omega
        """
        super().configure()
        model = self.config.get('ocean', 'model')
        compare = self.steps['compare']
        assert isinstance(compare, Compare)
        if model == 'mpas-ocean':
            # compare reads the mixed-layer depths too, which the runs write
            # but a Forward step does not declare
            for name in ['reference', 'shifted']:
                self.steps[name].add_output_file(filename=MLD_FILENAME)
            compare.filenames = ['output.nc', MLD_FILENAME]
        elif model == 'omega' and 'shifted_restart' not in self.steps:
            self._add_omega_restart(compare)

    def _add_omega_restart(self, compare: Compare) -> None:
        """
        Make ``shifted`` the full run of a restart, and add the run that
        continues from it
        """
        config = self.config
        run_duration = config.get('realistic_global_forward', 'run_duration')
        output_interval = config.get(
            'realistic_global_forward', 'output_interval'
        )
        restart_time = config.get('min_level_cell', 'restart_time')
        restart_duration = _duration_string(
            duration_to_seconds(run_duration)
            - duration_to_seconds(restart_time)
        )

        self.remove_step(self.steps['shifted'])
        self.remove_step(compare)

        shifted = RestartStep(
            component=self.component,
            name='shifted',
            subdir=f'{self.subdir}/shifted',
            init_condition=self.top_level_init,
            run_duration=run_duration,
            output_interval=output_interval,
            restart_time=restart_time,
        )
        shifted_restart = RestartStep(
            component=self.component,
            name='shifted_restart',
            subdir=f'{self.subdir}/shifted_restart',
            init_condition=self.top_level_init,
            run_duration=restart_duration,
            output_interval=output_interval,
            restart_time=restart_time,
            restart_from=shifted,
        )
        compare.restart_subdir = shifted_restart.name
        steps: List[Step] = [shifted, shifted_restart, compare]
        for step in steps:
            step.set_shared_config(config, link='min_level_cell.cfg')
            self.add_step(step)


def _duration_string(seconds: float) -> str:
    """An MPAS-style duration string (DDDD_HH:MM:SS) for ``seconds``"""
    total = int(round(seconds))
    days, rest = divmod(total, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)
    return f'{days:04d}_{hours:02d}:{minutes:02d}:{secs:02d}'
