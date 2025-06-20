from typing import Dict as Dict

from polaris import Step, Task
from polaris.resolution import resolution_to_string
from polaris.tasks.ocean.merry_go_round.default.viz import Viz
from polaris.tasks.ocean.merry_go_round.forward import Forward
from polaris.tasks.ocean.merry_go_round.init import Init


class Default(Task):
    """
    The default test case for the merry-go-round
    """

    def __init__(self, component, config, resolution, timestep, indir):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.ocean.Ocean
            The ocean component that this task belongs to

        config : polaris.config.PolarisConfigParser
            A shared config parser

        resolution : float
            The resolution of the test case in km

        timestep : float
            The timestep of the test case in seconds

        indir : str
            The directory the task is in, to which ``name`` will be appended
        """
        config_filename = 'merry_go_round.cfg'

        super().__init__(component=component, name='default', indir=indir)
        self.set_shared_config(config, link=config_filename)

        mesh_name = resolution_to_string(resolution)

        subdir = f'{indir}/init/{mesh_name}'
        symlink = f'init/{mesh_name}'
        init_step = Init(
            component=component,
            resolution=resolution,
            name=f'init_{mesh_name}',
            subdir=subdir,
        )
        init_step.set_shared_config(config, link=config_filename)
        self.add_step(init_step, symlink=symlink)

        subdir = f'{indir}/forward/{mesh_name}_{timestep}s'
        symlink = f'forward/{mesh_name}_{timestep}s'
        forward_step = Forward(
            component=component,
            refinement='both',
            refinement_factor=1,
            name=f'forward_{mesh_name}_{timestep}s',
            subdir=subdir,
            init=init_step,
        )
        forward_step.set_shared_config(config, link=config_filename)
        self.add_step(forward_step, symlink=symlink)

        viz_dependencies: Dict[str, Step] = dict(
            mesh=init_step, init=init_step, forward=forward_step
        )

        viz_step = Viz(
            component=component,
            dependencies=viz_dependencies,
            taskdir=self.subdir,
        )
        viz_step.set_shared_config(config, link=config_filename)
        self.add_step(viz_step, run_by_default=True)

        config.add_from_package(
            'polaris.tasks.ocean.merry_go_round', config_filename
        )
