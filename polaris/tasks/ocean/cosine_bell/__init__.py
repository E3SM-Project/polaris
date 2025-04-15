from math import ceil as ceil
from typing import Dict as Dict

from polaris import Step, Task
from polaris.config import PolarisConfigParser as PolarisConfigParser
from polaris.ocean.convergence import (
    get_resolution_for_task as get_resolution_for_task,
)
from polaris.ocean.convergence import (
    get_timestep_for_task as get_timestep_for_task,
)
from polaris.ocean.mesh.spherical import (
    add_spherical_base_mesh_step as add_spherical_base_mesh_step,
)
from polaris.tasks.ocean.cosine_bell.analysis import Analysis as Analysis
from polaris.tasks.ocean.cosine_bell.decomp import Decomp as Decomp
from polaris.tasks.ocean.cosine_bell.forward import Forward as Forward
from polaris.tasks.ocean.cosine_bell.init import Init as Init
from polaris.tasks.ocean.cosine_bell.restart import Restart as Restart
from polaris.tasks.ocean.cosine_bell.viz import Viz as Viz


def add_cosine_bell_tasks(component):
    """
    Add tasks that define variants of the cosine bell test case

    component : polaris.ocean.Ocean
        the ocean component that the tasks will be added to
    """

    for prefix, single_refinement in [('icos', 8.0), ('qu', 2.0)]:
        filepath = f'spherical/{prefix}/cosine_bell/cosine_bell.cfg'
        config = PolarisConfigParser(filepath=filepath)
        config.add_from_package('polaris.ocean.convergence', 'convergence.cfg')
        config.add_from_package(
            'polaris.ocean.convergence.spherical', 'spherical.cfg'
        )
        config.add_from_package(
            'polaris.tasks.ocean.cosine_bell', 'cosine_bell.cfg'
        )
        _set_convergence_configs(config, prefix)

        for refinement in ['both', 'space', 'time']:
            for include_viz in [False, True]:
                component.add_task(
                    CosineBell(
                        component=component,
                        config=config,
                        prefix=prefix,
                        include_viz=include_viz,
                        refinement=refinement,
                    )
                )

        component.add_task(
            Restart(
                component=component,
                config=config,
                prefix=prefix,
                refinement_factor=single_refinement,
                refinement='both',
            )
        )

        component.add_task(
            Decomp(
                component=component,
                config=config,
                prefix=prefix,
                refinement_factor=single_refinement,
                refinement='both',
                proc_counts=[12, 24],
            )
        )


class CosineBell(Task):
    """
    A convergence test for the advection of a cosine-bell tracer

    Attributes
    ----------
    refinement : str
        Refinement type. One of 'space', 'time' or 'both' indicating both
        space and time

    prefix : str
        The prefix on the mesh name, step names and a subdirectory in the
        work directory indicating the mesh type ('icos': uniform or
        'qu': less regular JIGSAW meshes)

    include_viz : bool
        Include VizMap and Viz steps for each resolution
    """

    def __init__(
        self, component, config, prefix, include_viz, refinement='both'
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

        include_viz : bool
            Include VizMap and Viz steps for each resolution

        refinement : str, optional
            Refinement type. One of 'space', 'time' or 'both' indicating both
            space and time
        """
        subdir = f'spherical/{prefix}/cosine_bell/convergence_{refinement}'
        name = f'{prefix}_cosine_bell_convergence_{refinement}'
        if include_viz:
            subdir = f'{subdir}/with_viz'
            name = f'{name}_with_viz'
        link = 'cosine_bell.cfg'
        super().__init__(component=component, name=name, subdir=subdir)
        self.refinement = refinement
        self.prefix = prefix
        self.include_viz = include_viz

        self.set_shared_config(config, link=link)

        self._setup_steps(refinement=refinement)

    def configure(self):
        """
        Set config options for the test case
        """
        super().configure()

        # set up the steps again in case a user has provided new resolutions
        self._setup_steps(self.refinement)

    def _setup_steps(self, refinement):
        """
        setup steps given resolutions

        Parameters
        ----------
        refinement : str
           refinement type. One of 'space', 'time' or 'both'
        """
        prefix = self.prefix
        config = self.config
        config_filename = self.config_filename

        if refinement == 'time':
            option = 'refinement_factors_time'
        else:
            option = 'refinement_factors_space'

        _set_convergence_configs(config, prefix)

        refinement_factors = config.getlist('convergence', option, dtype=float)

        # start fresh with no steps
        for step in list(self.steps.values()):
            self.remove_step(step)

        component = self.component

        analysis_dependencies: Dict[str, Dict[str, Step]] = dict(
            mesh=dict(), init=dict(), forward=dict()
        )

        resolutions = list()
        timesteps = list()

        case_dir = f'spherical/{prefix}/cosine_bell'

        for refinement_factor in refinement_factors:
            resolution = get_resolution_for_task(
                config, refinement_factor, refinement=refinement
            )

            base_mesh_step, mesh_name = add_spherical_base_mesh_step(
                component, resolution, icosahedral=(prefix == 'icos')
            )
            analysis_dependencies['mesh'][refinement_factor] = base_mesh_step

            name = f'{prefix}_init_{mesh_name}'
            subdir = f'{case_dir}/init/{mesh_name}'
            if subdir in component.steps:
                init_step = component.steps[subdir]
            else:
                init_step = Init(
                    component=component,
                    name=name,
                    subdir=subdir,
                    base_mesh=base_mesh_step,
                )
                init_step.set_shared_config(config, link=config_filename)
            analysis_dependencies['init'][refinement_factor] = init_step

            if resolution not in resolutions:
                self.add_step(base_mesh_step, symlink=f'base_mesh/{mesh_name}')
                self.add_step(init_step, symlink=f'init/{mesh_name}')
                resolutions.append(resolution)

            timestep, _ = get_timestep_for_task(
                config, refinement_factor, refinement=refinement
            )
            timestep = ceil(timestep)
            timesteps.append(timestep)

            subdir = f'{case_dir}/forward/{mesh_name}_{timestep}s'
            symlink = f'forward/{mesh_name}_{timestep}s'
            if subdir in component.steps:
                forward_step = component.steps[subdir]
            else:
                name = f'{prefix}_forward_{mesh_name}_{timestep}s'
                forward_step = Forward(
                    component=component,
                    name=name,
                    subdir=subdir,
                    refinement_factor=refinement_factor,
                    mesh=base_mesh_step,
                    init=init_step,
                    refinement=refinement,
                )
                forward_step.set_shared_config(config, link=config_filename)
            self.add_step(forward_step, symlink=symlink)
            analysis_dependencies['forward'][refinement_factor] = forward_step

            if self.include_viz:
                name = f'{prefix}_viz_{mesh_name}_{timestep}s'
                subdir = f'{case_dir}/viz/{mesh_name}_{timestep}s'
                if subdir in component.steps:
                    viz_step = component.steps[subdir]
                else:
                    viz_step = Viz(
                        component=component,
                        name=name,
                        subdir=subdir,
                        base_mesh=base_mesh_step,
                        init=init_step,
                        forward=forward_step,
                        mesh_name=mesh_name,
                    )
                    viz_step.set_shared_config(config, link=config_filename)
                self.add_step(viz_step)

        subdir = f'{case_dir}/convergence_{refinement}/analysis'
        if subdir in component.steps:
            step = component.steps[subdir]
            step.resolutions = resolutions
            step.dependencies_dict = analysis_dependencies
        else:
            step = Analysis(
                component=component,
                subdir=subdir,
                dependencies=analysis_dependencies,
                refinement=refinement,
            )
            step.set_shared_config(config, link=config_filename)
        if self.include_viz:
            symlink = f'analysis_{refinement}'
            self.add_step(step, symlink=symlink)
        else:
            self.add_step(step)


def _set_convergence_configs(config, prefix):
    for refinement in ['space', 'time']:
        option = f'refinement_factors_{refinement}'
        refinement_factors = config.getlist(
            'spherical_convergence', f'{prefix}_{option}', dtype=str
        )
        refinement_factors = ', '.join(refinement_factors)
        config.set('convergence', option, value=refinement_factors)

        base_resolution = config.getfloat(
            'spherical_convergence', f'{prefix}_base_resolution'
        )
        config.set(
            'convergence', 'base_resolution', value=f'{base_resolution:03g}'
        )
