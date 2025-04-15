from polaris import Task as Task
from polaris.mesh.add_step import add_uniform_spherical_base_mesh_step
from polaris.ocean.convergence import (
    get_resolution_for_task as get_resolution_for_task,
)
from polaris.tasks.ocean.cosine_bell.init import Init as Init
from polaris.tasks.ocean.cosine_bell.restart.restart_step import (
    RestartStep as RestartStep,
)
from polaris.tasks.ocean.cosine_bell.validate import Validate as Validate


class Restart(Task):
    """
    A cosine bell restart test case, which makes sure the model produces
    identical results with one longer run and two shorter runs with a restart
    in between.
    """

    def __init__(
        self, component, config, prefix, refinement_factor, refinement
    ):
        """
        Create the convergence test

        Parameters
        ----------
        component : polaris.ocean.Ocean
            The ocean component that this task belongs to

        config : polaris.config.PolarisConfigParser
            A shared config parser

        prefix : str
            The prefix on the mesh name, step names and a subdirectory in the
            work directory indicating the mesh type ('icos': uniform or
            'qu': less regular JIGSAW meshes)

        refinement_factor : float
            The factor by which to scale space, time or both

        refinement : str
            Refinement type. One of 'space', 'time' or 'both' indicating both
            space and time
        """

        task_subdir = f'spherical/{prefix}/cosine_bell/restart'
        name = f'{prefix}_cosine_bell_restart'
        config_filename = 'cosine_bell.cfg'

        super().__init__(component=component, name=name, subdir=task_subdir)

        self.set_shared_config(config, link=config_filename)

        resolution = get_resolution_for_task(
            config, refinement_factor, refinement=refinement
        )

        icosahedral = prefix == 'icos'
        base_mesh_step, mesh_name = add_uniform_spherical_base_mesh_step(
            resolution, icosahedral
        )

        name = f'{prefix}_init_{mesh_name}'
        init_subdir = f'spherical/{prefix}/cosine_bell/init/{mesh_name}'
        if init_subdir in component.steps:
            init_step = component.steps[init_subdir]
        else:
            init_step = Init(
                component=component,
                name=name,
                subdir=init_subdir,
                base_mesh=base_mesh_step,
            )
            init_step.set_shared_config(config, link=config_filename)

        self.add_step(base_mesh_step, symlink=f'base_mesh/{mesh_name}')
        self.add_step(init_step, symlink=f'init/{mesh_name}')

        step_names = ['full_run', 'restart_run']
        for name in step_names:
            subdir = f'{task_subdir}/{name}'
            do_restart = name == 'restart_run'
            step = RestartStep(
                component=component,
                name=name,
                subdir=subdir,
                mesh=base_mesh_step,
                init=init_step,
                refinement_factor=refinement_factor,
                refinement=refinement,
                do_restart=do_restart,
            )
            step.set_shared_config(config, link=config_filename)
            self.add_step(step)

        self.add_step(
            Validate(
                component=component, step_subdirs=step_names, indir=task_subdir
            )
        )
