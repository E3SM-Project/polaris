from math import ceil as ceil
from typing import Dict as Dict

from polaris import Step, Task
from polaris.config import PolarisConfigParser as PolarisConfigParser
from polaris.mesh.base import add_uniform_spherical_base_mesh_step
from polaris.ocean.convergence import (
    get_resolution_for_task as get_resolution_for_task,
)
from polaris.ocean.convergence import (
    get_timestep_for_task as get_timestep_for_task,
)
from polaris.tasks.ocean.external_gravity_wave.analysis import (
    Analysis as Analysis,
)
from polaris.tasks.ocean.external_gravity_wave.forward import (
    Forward as Forward,
)
from polaris.tasks.ocean.external_gravity_wave.forward import (
    ReferenceForward as ReferenceForward,
)
from polaris.tasks.ocean.external_gravity_wave.init import Init as Init
from polaris.tasks.ocean.external_gravity_wave.lts_regions import (
    LTSRegions as LTSRegions,
)


def add_external_gravity_wave_tasks(component):
    """
    Add tasks that define variants of the external gravity wave test case

    component : polaris.tasks.ocean.Ocean
        the ocean component that the tasks will be added to
    """

    for prefix in ['icos', 'qu']:
        for dt_type in ['global', 'local']:
            egw = 'external_gravity_wave'
            filepath = (
                f'spherical/{prefix}/{egw}/{dt_type}_time_step/'
                f'egw_{dt_type}_time_step.cfg'
            )
            config = PolarisConfigParser(filepath=filepath)
            config.add_from_package(
                'polaris.ocean.convergence', 'convergence.cfg'
            )
            config.add_from_package(
                'polaris.ocean.convergence.spherical', 'spherical.cfg'
            )
            config.add_from_package(f'polaris.tasks.ocean.{egw}', f'{egw}.cfg')
            config.add_from_package(
                f'polaris.tasks.ocean.{egw}', f'egw_{dt_type}_time_step.cfg'
            )
            _set_convergence_configs(config, prefix)

            component.add_task(
                ExternalGravityWave(
                    component=component,
                    config=config,
                    prefix=prefix,
                    refinement='time',
                    dt_type=dt_type,
                )
            )


class ExternalGravityWave(Task):
    """
    A convergence test via a simple external gravity wave on an
    aquaplanet.

    Attributes
    ----------
    refinement : str
        Refinement type. One of 'space', 'time' or 'both' indicating both
        space and time

    prefix : str
        The prefix on the mesh name, step names and a subdirectory in the
        work directory indicating the mesh type ('icos': uniform or
        'qu': less regular JIGSAW meshes)
    """

    def __init__(
        self,
        component,
        config,
        prefix,
        refinement='both',
        dt_type='global',
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

        refinement : str, optional
            Refinement type. One of 'space', 'time' or 'both' indicating both
            space and time

        dt_type : str, optional
            Type of time-stepping to use. One of 'global' or 'local'
        """
        egw = 'external_gravity_wave'
        subdir = (
            f'spherical/{prefix}/{egw}/{dt_type}_time_step/'
            f'convergence_{refinement}'
        )
        name = f'{prefix}_{egw}_{dt_type}_time_step_convergence_{refinement}'
        link = 'external_gravity_wave.cfg'
        super().__init__(component=component, name=name, subdir=subdir)
        self.refinement = refinement
        self.prefix = prefix
        self.dt_type = dt_type

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
        dt_type = self.dt_type

        if refinement == 'time':
            option = 'refinement_factors_time'
        else:
            raise ValueError(
                f'refinement {refinement} not supported for the '
                'external gravity wave case'
            )

        _set_convergence_configs(config, prefix)

        refinement_factors = config.getlist('convergence', option, dtype=float)
        ref_solution_factor = self.config.getfloat(
            'convergence',
            'ref_soln_refinement_factor_time',
        )

        # start fresh with no steps
        for step in list(self.steps.values()):
            self.remove_step(step)

        component = self.component

        analysis_dependencies: Dict[str, Dict[str, Step]] = dict(
            mesh=dict(), init=dict(), forward=dict()
        )

        resolutions = list()
        timesteps = list()

        case_dir = (
            f'spherical/{prefix}/external_gravity_wave/{dt_type}_time_step'
        )

        resolution = get_resolution_for_task(
            config, refinement_factors[0], refinement=refinement
        )

        base_mesh_step, mesh_name = add_uniform_spherical_base_mesh_step(
            resolution, icosahedral=(prefix == 'icos')
        )

        name = f'{prefix}_init_{mesh_name}'
        subdir = f'spherical/{prefix}/external_gravity_wave/init/{mesh_name}'
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

        if dt_type == 'local':
            name = f'{prefix}_init_lts_{mesh_name}'
            subdir = f'{case_dir}/init_lts/{mesh_name}'
            if subdir in component.steps:
                lts_step = component.steps[subdir]
            else:
                lts_step = LTSRegions(
                    component, init_step, name=name, subdir=subdir
                )
                lts_step.set_shared_config(config, link=config_filename)

        if resolution not in resolutions:
            self.add_step(base_mesh_step, symlink=f'base_mesh/{mesh_name}')
            self.add_step(init_step, symlink=f'init/{mesh_name}')
            if dt_type == 'local':
                self.add_step(lts_step, symlink=f'init_lts/{mesh_name}')
                init_step = lts_step
            resolutions.append(resolution)

        section = config['convergence_forward']
        time_integrator = section.get('time_integrator')
        # dt is proportional to resolution: default 30 seconds per km
        if (
            time_integrator == 'RK4'
            or time_integrator == 'LTS'
            or time_integrator == 'FB_LTS'
        ):
            dt_per_km = section.getfloat('rk4_dt_per_km')
        else:
            dt_per_km = section.getfloat('split_dt_per_km')

        dt = dt_per_km * ref_solution_factor * resolution
        timestep = ceil(dt)
        subdir = f'{case_dir}/forward/{mesh_name}_{timestep}s'
        symlink = f'forward/{mesh_name}_{timestep}s'
        if subdir in component.steps:
            ref_forward_step = component.steps[subdir]
        else:
            name = f'{prefix}_forward_{mesh_name}_{timestep}s'
            ref_forward_step = ReferenceForward(
                component=component,
                resolution=resolution,
                name=name,
                subdir=subdir,
                mesh=base_mesh_step,
                init=init_step,
                dt_type=dt_type,
                dt=dt,
            )
            ref_forward_step.set_shared_config(config, link=config_filename)
        self.add_step(ref_forward_step, symlink=symlink)
        analysis_dependencies['mesh'][ref_solution_factor] = base_mesh_step
        analysis_dependencies['init'][ref_solution_factor] = init_step
        analysis_dependencies['forward'][ref_solution_factor] = (
            ref_forward_step
        )

        for refinement_factor in refinement_factors:
            analysis_dependencies['mesh'][refinement_factor] = base_mesh_step
            analysis_dependencies['init'][refinement_factor] = init_step

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
                    dt_type=dt_type,
                )
                forward_step.set_shared_config(config, link=config_filename)
            self.add_step(forward_step, symlink=symlink)
            analysis_dependencies['forward'][refinement_factor] = forward_step

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
                ref_solution_factor=ref_solution_factor,
            )
            step.set_shared_config(config, link=config_filename)
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
            'convergence', 'base_resolution', value=f'{base_resolution:g}'
        )
