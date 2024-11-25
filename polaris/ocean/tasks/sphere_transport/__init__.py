from math import ceil
from typing import Dict

from polaris import Step, Task
from polaris.config import PolarisConfigParser
from polaris.ocean.convergence import (
    get_resolution_for_task,
    get_timestep_for_task,
)
from polaris.ocean.mesh.spherical import add_spherical_base_mesh_step
from polaris.ocean.tasks.sphere_transport.analysis import Analysis
from polaris.ocean.tasks.sphere_transport.filament_analysis import (
    FilamentAnalysis,
)
from polaris.ocean.tasks.sphere_transport.forward import Forward
from polaris.ocean.tasks.sphere_transport.init import Init
from polaris.ocean.tasks.sphere_transport.mixing_analysis import MixingAnalysis
from polaris.ocean.tasks.sphere_transport.viz import Viz


def add_sphere_transport_tasks(component):
    """
    Add tasks that define variants of sphere transport test cases:
    nondivergent_2d, divergent_2d, correlated_tracers_2d, rotation_2d

    component : polaris.ocean.Ocean
        the ocean component that the tasks will be added to
    """

    for icosahedral, prefix in [(True, 'icos'), (False, 'qu')]:
        for case_name in ['rotation_2d', 'nondivergent_2d', 'divergent_2d',
                          'correlated_tracers_2d']:
            filepath = f'spherical/{prefix}/{case_name}/{case_name}.cfg'
            config = PolarisConfigParser(filepath=filepath)
            config.add_from_package('polaris.ocean.convergence',
                                    'convergence.cfg')
            config.add_from_package('polaris.ocean.convergence.spherical',
                                    'spherical.cfg')
            package = 'polaris.ocean.tasks.sphere_transport'
            config.add_from_package(package, 'sphere_transport.cfg')
            config.add_from_package(package, f'{case_name}.cfg')
            for include_viz in [False, True]:
                component.add_task(SphereTransport(
                    component=component, case_name=case_name,
                    icosahedral=icosahedral, config=config,
                    include_viz=include_viz))


class SphereTransport(Task):
    """
    A test case for testing properties of tracer advection

    Attributes
    ----------
    resolutions : list of float
        A list of mesh resolutions

    refinement : str
        Refinement type. One of 'space', 'time' or 'both' indicating both
        space and time

    icosahedral : bool
        Whether to use icosahedral, as opposed to less regular, JIGSAW meshes

    include_viz : bool
        Include VizMap and Viz steps for each resolution
    """
    def __init__(self, component, config, case_name, icosahedral, include_viz,
                 refinement='both'):
        """
        Create test case for creating a global MPAS-Ocean mesh

        Parameters
        ----------
        component : polaris.ocean.Ocean
            The ocean component that this task belongs to

        config : polaris.config.PolarisConfigParser
            A shared config parser

        case_name: string
            The name of the case which determines what variant of the
            configuration to use

        icosahedral : bool
            Whether to use icosahedral, as opposed to less regular, JIGSAW
            meshes

        include_viz : bool
            Include VizMap and Viz steps for each resolution

        refinement : str, optional
            Refinement type. One of 'space', 'time' or 'both' indicating both
            space and time
        """
        if icosahedral:
            prefix = 'icos'
        else:
            prefix = 'qu'

        subdir = f'spherical/{prefix}/{case_name}'
        name = f'{prefix}_{case_name}'
        if include_viz:
            subdir = f'{subdir}/with_viz'
            name = f'{name}_with_viz'
            link = f'{case_name}.cfg'
        else:
            # config options live in the task already so no need for a symlink
            link = None
        super().__init__(component=component, name=name, subdir=subdir)
        self.resolutions = list()
        self.refinement = refinement
        self.icosahedral = icosahedral
        self.case_name = case_name
        self.include_viz = include_viz

        self.set_shared_config(config, link=link)

        # add the steps with default resolutions so they can be listed
        self._setup_steps(refinement=refinement)

    def configure(self):
        """
        Set config options for the test case
        """
        super().configure()

        # set up the steps again in case a user has provided new resolutions
        self._setup_steps(self.refinement)

    def _setup_steps(self, refinement):  # noqa: C901
        """ setup steps given resolutions """
        case_name = self.case_name
        icosahedral = self.icosahedral
        config = self.config
        config_filename = self.config_filename

        if icosahedral:
            prefix = 'icos'
        else:
            prefix = 'qu'

        if refinement == 'time':
            option = 'refinement_factors_time'
        else:
            option = 'refinement_factors_space'
        refinement_factors = config.getlist('spherical_convergence',
                                            f'{prefix}_{option}', dtype=str)
        refinement_factors = ', '.join(refinement_factors)
        config.set('convergence', option, value=refinement_factors)
        refinement_factors = config.getlist('convergence',
                                            option, dtype=float)

        base_resolution = config.getfloat('spherical_convergence',
                                          f'{prefix}_base_resolution')
        config.set('convergence', 'base_resolution',
                   value=f'{base_resolution:03g}')

        # start fresh with no steps
        for step in list(self.steps.values()):
            self.remove_step(step)

        resolutions = self.resolutions

        component = self.component

        sph_trans_dir = f'spherical/{prefix}/{case_name}'

        analysis_dependencies: Dict[str, Dict[str, Step]] = (
            dict(mesh=dict(), init=dict(), forward=dict()))
        timesteps = list()
        for idx, refinement_factor in enumerate(refinement_factors):
            resolution = get_resolution_for_task(
                config, refinement_factor, refinement=refinement)
            base_mesh_step, mesh_name = add_spherical_base_mesh_step(
                component, resolution, icosahedral)
            analysis_dependencies['mesh'][refinement_factor] = base_mesh_step

            name = f'{prefix}_init_{mesh_name}'
            subdir = f'{sph_trans_dir}/init/{mesh_name}'
            if self.include_viz:
                symlink = f'init/{mesh_name}'
            else:
                symlink = None
            if subdir in component.steps:
                init_step = component.steps[subdir]
            else:
                init_step = Init(component=component, name=name,
                                 subdir=subdir, base_mesh=base_mesh_step,
                                 case_name=case_name)
                init_step.set_shared_config(config, link=config_filename)
            analysis_dependencies['init'][refinement_factor] = init_step
            self.add_step(base_mesh_step, symlink=f'base_mesh/{mesh_name}')
            self.add_step(init_step, symlink=symlink)
            if resolution not in resolutions:
                resolutions.append(resolution)

            timestep, _ = get_timestep_for_task(
                config, refinement_factor, refinement=refinement)
            timestep = ceil(timestep)
            timesteps.append(timestep)
            name = f'{prefix}_forward_{mesh_name}_{timestep}s'
            subdir = f'{sph_trans_dir}/forward/{mesh_name}_{timestep}s'
            if self.include_viz:
                symlink = f'forward/{mesh_name}_{timestep}s'
            else:
                symlink = None
            if subdir in component.steps:
                forward_step = component.steps[subdir]
            else:
                forward_step = Forward(
                    component=component, name=name,
                    subdir=subdir,
                    base_mesh=base_mesh_step,
                    init=init_step,
                    case_name=case_name,
                    refinement_factor=refinement_factor,
                    refinement=refinement)
                forward_step.set_shared_config(config, link=config_filename)
            self.add_step(forward_step, symlink=symlink)
            analysis_dependencies['forward'][refinement_factor] = forward_step

            if self.include_viz:
                with_viz_dir = f'{sph_trans_dir}/with_viz'
                name = f'{prefix}_viz_{mesh_name}_{timestep}s'
                subdir = f'{with_viz_dir}/viz/{mesh_name}_{timestep}s'
                step = Viz(component=component, name=name,
                           subdir=subdir, base_mesh=base_mesh_step,
                           init=init_step, forward=forward_step,
                           mesh_name=mesh_name)
                step.set_shared_config(config, link=config_filename)
                self.add_step(step)

        subdir = f'{sph_trans_dir}/analysis/{refinement}'
        if self.include_viz:
            symlink = f'analysis_{refinement}'
        else:
            symlink = None
        if subdir in component.steps:
            step = component.steps[subdir]
            step.resolutions = resolutions
            step.dependencies_dict = analysis_dependencies
        else:
            step = Analysis(component=component,
                            subdir=subdir, case_name=case_name,
                            dependencies=analysis_dependencies,
                            refinement=refinement)
            step.set_shared_config(config, link=config_filename)
        self.add_step(step, symlink=symlink)

        if case_name == 'correlated_tracers_2d':
            subdir = f'{sph_trans_dir}/mixing_analysis'
            if self.include_viz:
                symlink = 'mixing_analysis'
            else:
                symlink = None
            if subdir in component.steps:
                step = component.steps[subdir]
            else:
                step = MixingAnalysis(component=component,
                                      icosahedral=icosahedral, subdir=subdir,
                                      refinement_factors=refinement_factors,
                                      case_name=case_name,
                                      dependencies=analysis_dependencies,
                                      refinement=refinement)
            step.set_shared_config(config, link=config_filename)
            self.add_step(step, symlink=symlink)

        if case_name == 'nondivergent_2d':
            subdir = f'{sph_trans_dir}/filament_analysis'
            if self.include_viz:
                symlink = 'filament_analysis'
            else:
                symlink = None
            if subdir in component.steps:
                step = component.steps[subdir]
            else:
                step = FilamentAnalysis(component=component,
                                        refinement_factors=refinement_factors,
                                        icosahedral=icosahedral, subdir=subdir,
                                        case_name=case_name,
                                        dependencies=analysis_dependencies,
                                        refinement=refinement)
            step.set_shared_config(config, link=config_filename)
            self.add_step(step, symlink=symlink)
