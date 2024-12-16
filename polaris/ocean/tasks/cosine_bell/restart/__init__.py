from polaris import Task
from polaris.ocean.convergence import get_resolution_for_task
from polaris.ocean.mesh.spherical import add_spherical_base_mesh_step
from polaris.ocean.tasks.cosine_bell.init import Init
from polaris.ocean.tasks.cosine_bell.restart.restart_step import RestartStep
from polaris.ocean.tasks.cosine_bell.validate import Validate


class Restart(Task):
    """
    A cosine bell restart test case, which makes sure the model produces
    identical results with one longer run and two shorter runs with a restart
    in between.
    """

    def __init__(self, component, config, icosahedral, refinement_factor,
                 refinement):
        """
        Create the convergence test

        Parameters
        ----------
        component : polaris.ocean.Ocean
            The ocean component that this task belongs to

        config : polaris.config.PolarisConfigParser
            A shared config parser

        icosahedral : bool
            Whether to use icosahedral, as opposed to less regular, JIGSAW
            meshes

        refinement_factor : float
            The factor by which to scale space, time or both

        refinement : str
            Refinement type. One of 'space', 'time' or 'both' indicating both
            space and time
        """

        if icosahedral:
            prefix = 'icos'
        else:
            prefix = 'qu'

        task_subdir = f'spherical/{prefix}/cosine_bell/restart'
        name = f'{prefix}_cosine_bell_restart'
        config_filename = 'cosine_bell.cfg'

        super().__init__(component=component, name=name, subdir=task_subdir)

        self.set_shared_config(config, link=config_filename)

        resolution = get_resolution_for_task(
            config, refinement_factor, refinement=refinement)

        base_mesh_step, mesh_name = add_spherical_base_mesh_step(
            component, resolution, icosahedral)

        name = f'{prefix}_init_{mesh_name}'
        init_subdir = f'spherical/{prefix}/cosine_bell/init/{mesh_name}'
        if init_subdir in component.steps:
            init_step = component.steps[init_subdir]
        else:
            init_step = Init(component=component, name=name,
                             subdir=init_subdir, base_mesh=base_mesh_step)
            init_step.set_shared_config(config, link=config_filename)

        self.add_step(base_mesh_step, symlink=f'base_mesh/{mesh_name}')
        self.add_step(init_step, symlink=f'init/{mesh_name}')

        step_names = ['full_run', 'restart_run']
        for name in step_names:
            subdir = f'{task_subdir}/{name}'
            step = RestartStep(
                component=component, name=name, subdir=subdir,
                mesh=base_mesh_step, init=init_step,
                refinement_factor=refinement_factor,
                refinement=refinement)
            step.set_shared_config(
                config, link=config_filename)
            self.add_step(step)

        self.add_step(Validate(component=component,
                               step_subdirs=step_names,
                               indir=task_subdir))
