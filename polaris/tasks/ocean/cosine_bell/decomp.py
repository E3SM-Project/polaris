from polaris import Task
from polaris.mesh.add_step import add_uniform_spherical_base_mesh_step
from polaris.ocean.convergence import get_resolution_for_task
from polaris.tasks.ocean.cosine_bell.forward import Forward
from polaris.tasks.ocean.cosine_bell.init import Init
from polaris.tasks.ocean.cosine_bell.validate import Validate


class Decomp(Task):
    """
    A cosine bell decomposition task, which makes sure the model produces
    identical results on different numbers of cores.
    """

    def __init__(
        self,
        component,
        config,
        prefix,
        refinement_factor,
        refinement,
        proc_counts,
    ):
        """
        Create the convergence test

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
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

        proc_counts : list of int
            The number of processors to run each step on
        """
        task_subdir = f'spherical/{prefix}/cosine_bell/decomp'
        name = f'{prefix}_cosine_bell_decomp'
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

        step_names = []
        for procs in proc_counts:
            name = f'{procs}proc'
            step_names.append(name)
            subdir = f'{task_subdir}/{name}'
            step = Forward(
                component=component,
                name=name,
                subdir=subdir,
                mesh=base_mesh_step,
                init=init_step,
                refinement_factor=refinement_factor,
                refinement=refinement,
            )
            step.dynamic_ntasks = False
            step.ntasks = procs
            step.min_tasks = procs
            step.set_shared_config(config, link=config_filename)
            self.add_step(step)

        self.add_step(
            Validate(
                component=component, step_subdirs=step_names, indir=task_subdir
            )
        )
