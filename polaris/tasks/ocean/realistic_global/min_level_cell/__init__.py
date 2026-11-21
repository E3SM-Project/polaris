from typing import List

from polaris import Step, Task
from polaris.config import PolarisConfigParser
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
    compare_shifted as compare_shifted,
)


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

        shifted = Forward(
            component=component,
            name='shifted',
            subdir=f'{subdir}/shifted',
            init_condition=TopLevelInitialCondition(add_top_level),
            validate_class='state',
        )

        steps: List[Step] = [reference, add_top_level, shifted]
        for step in steps:
            step.set_shared_config(config, link=config_filename)
            self.add_step(step)

        # compare reads the mixed-layer depths too, which the runs write but a
        # Forward step does not declare
        for forward in [reference, shifted]:
            forward.add_output_file(filename=MLD_FILENAME)

        compare = Compare(
            component=component,
            indir=subdir,
            reference_subdir=reference.name,
            shifted_subdir=shifted.name,
        )
        compare.set_shared_config(config, link=config_filename)
        self.add_step(compare)

    def configure(self):
        """
        Leave the task out for Omega, which reads its level indices from a
        vertical-coordinate file that ``add_top_level`` does not yet write
        """
        super().configure()
        model = self.config.get('ocean', 'model')
        if model != 'mpas-ocean':
            self.skip_reason = (
                f'the min_level_cell task supports only MPAS-Ocean so far, '
                f'not {model}'
            )
