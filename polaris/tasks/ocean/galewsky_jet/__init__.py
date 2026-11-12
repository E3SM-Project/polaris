from math import ceil
from typing import Dict

from polaris import Step, Task
from polaris.config import PolarisConfigParser
from polaris.constants import get_constant
from polaris.mesh.base import add_spherical_base_mesh_step
from polaris.ocean.convergence import (
    get_resolution_for_task,
    get_timestep_for_task,
)
from polaris.tasks.ocean.galewsky_jet.comparison import (
    AdjustmentAnalysis,
    UnstableAnalysis,
)
from polaris.tasks.ocean.galewsky_jet.forward import Forward
from polaris.tasks.ocean.galewsky_jet.init import Init
from polaris.tasks.ocean.galewsky_jet.steady_state import (
    SteadyStateAnalysis,
    SteadyStateViz,
)

TASK_NAMES = ['steady_state', 'adjustment', 'unstable']


def add_galewsky_jet_tasks(component):
    """
    Add the tasks for the barotropically unstable jet of Galewsky, Scott &
    Polvani (2004) on icosahedral and quasi-uniform meshes

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        the ocean component that the tasks will be added to
    """
    for icosahedral, prefix in [(True, 'icos'), (False, 'qu')]:
        filepath = (
            f'{component.name}/spherical/{prefix}/galewsky_jet/'
            f'galewsky_jet.cfg'
        )
        config = PolarisConfigParser(filepath=filepath)
        config.add_from_package('polaris.ocean.eos', 'constant.cfg')
        config.add_from_package('polaris.ocean.convergence', 'convergence.cfg')
        config.add_from_package(
            'polaris.ocean.convergence.spherical', 'spherical.cfg'
        )
        config.add_from_package(
            'polaris.tasks.ocean.galewsky_jet', 'galewsky_jet.cfg'
        )
        # Set rhoref to the PCD value only at setup so that if the
        # user wants to run with a different value by changing the cfg
        # before runtime, they can
        config.set(
            'ocean',
            'eos_constant_rhoref',
            value=f'{get_constant("seawater_density_reference"):02g}',
        )

        for task_name in TASK_NAMES:
            component.add_task(
                GalewskyJet(
                    component=component,
                    config=config,
                    icosahedral=icosahedral,
                    task_name=task_name,
                )
            )


class GalewskyJet(Task):
    """
    One stage of the Galewsky et al. (2004) test at a sequence of
    resolutions: the unperturbed jet without diffusion (``steady_state``),
    the perturbed jet's first 6 hours without diffusion (``adjustment``),
    or the perturbed jet for 6 days with diffusion (``unstable``)

    Attributes
    ----------
    icosahedral : bool
        Whether to use icosahedral, as opposed to quasi-uniform, meshes

    task_name : str
        The stage: ``steady_state``, ``adjustment`` or ``unstable``
    """

    def __init__(self, component, config, icosahedral, task_name):
        """
        Create the task

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this task belongs to

        config : polaris.config.PolarisConfigParser
            A shared config parser

        icosahedral : bool
            Whether to use icosahedral, as opposed to quasi-uniform, meshes

        task_name : str
            The stage: ``steady_state``, ``adjustment`` or ``unstable``
        """
        prefix = 'icos' if icosahedral else 'qu'
        subdir = f'spherical/{prefix}/galewsky_jet/{task_name}'
        name = f'{prefix}_galewsky_jet_{task_name}'
        super().__init__(component=component, name=name, subdir=subdir)
        self.icosahedral = icosahedral
        self.task_name = task_name

        self.set_shared_config(config, link='galewsky_jet.cfg')

        self._setup_steps()

    def configure(self):
        """
        Set config options for the task
        """
        super().configure()

        # set up the steps again in case a user has provided new resolutions
        self._setup_steps()

    def _setup_steps(self):
        """
        Set up the steps for the resolutions in the config options
        """
        config = self.config
        config_filename = self.config_filename
        task_name = self.task_name
        prefix = 'icos' if self.icosahedral else 'qu'

        factor_strings = config.getlist(
            'spherical_convergence',
            f'{prefix}_refinement_factors_space',
            dtype=str,
        )
        config.set(
            'convergence',
            'refinement_factors_space',
            value=', '.join(factor_strings),
        )
        refinement_factors = config.getlist(
            'convergence', 'refinement_factors_space', dtype=float
        )
        base_resolution = config.getfloat(
            'spherical_convergence', f'{prefix}_base_resolution'
        )
        config.set(
            'convergence', 'base_resolution', value=f'{base_resolution:03g}'
        )

        # start fresh with no steps
        for step in list(self.steps.values()):
            self.remove_step(step)

        component = self.component
        case_dir = f'spherical/{prefix}/galewsky_jet'
        perturbed = task_name != 'steady_state'
        init_kind = 'perturbed' if perturbed else 'balanced'

        dependencies: Dict[str, Dict[float, Step]] = dict(
            mesh=dict(), init=dict(), forward=dict()
        )
        resolutions: Dict[str, Dict[str, Step]] = dict()

        for refinement_factor in refinement_factors:
            resolution = get_resolution_for_task(config, refinement_factor)
            base_mesh_step, mesh_name = add_spherical_base_mesh_step(
                prefix=prefix, min_res=resolution
            )
            self.add_step(base_mesh_step, symlink=f'base_mesh/{mesh_name}')

            init_step = component.get_or_create_shared_step(
                step_cls=Init,
                subdir=f'{case_dir}/init/{init_kind}/{mesh_name}',
                config=config,
                config_filename=config_filename,
                name=f'{prefix}_init_{init_kind}_{mesh_name}',
                base_mesh=base_mesh_step,
                perturbed=perturbed,
            )
            self.add_step(init_step, symlink=f'init/{mesh_name}')

            timestep, _ = get_timestep_for_task(config, refinement_factor)
            timestep = ceil(timestep)
            forward_step = component.get_or_create_shared_step(
                step_cls=Forward,
                subdir=f'{self.subdir}/forward/{mesh_name}_{timestep}s',
                config=config,
                config_filename=config_filename,
                name=f'{prefix}_forward_{task_name}_{mesh_name}_{timestep}s',
                refinement_factor=refinement_factor,
                mesh=base_mesh_step,
                init=init_step,
                task_name=task_name,
            )
            self.add_step(forward_step)

            dependencies['mesh'][refinement_factor] = base_mesh_step
            dependencies['init'][refinement_factor] = init_step
            dependencies['forward'][refinement_factor] = forward_step
            resolutions[mesh_name] = dict(init=init_step, forward=forward_step)

            if task_name == 'steady_state':
                viz_step = component.get_or_create_shared_step(
                    step_cls=SteadyStateViz,
                    subdir=f'{self.subdir}/viz/{mesh_name}_{timestep}s',
                    config=config,
                    config_filename=config_filename,
                    name=f'{prefix}_viz_{task_name}_{mesh_name}_{timestep}s',
                    init=init_step,
                    forward=forward_step,
                    mesh_name=mesh_name,
                )
                self.add_step(viz_step)

        subdir = f'{self.subdir}/analysis'
        if task_name == 'steady_state':
            step = component.get_or_create_shared_step(
                step_cls=SteadyStateAnalysis,
                subdir=subdir,
                config=config,
                config_filename=config_filename,
                dependencies=dependencies,
                mesh_type=prefix,
            )
            # update the dependencies in case they have changed since the
            # step was created
            step.dependencies_dict = dependencies
        else:
            analysis_cls = (
                AdjustmentAnalysis
                if task_name == 'adjustment'
                else UnstableAnalysis
            )
            step = component.get_or_create_shared_step(
                step_cls=analysis_cls,
                subdir=subdir,
                config=config,
                config_filename=config_filename,
                resolutions=resolutions,
            )
            # update the resolutions in case they have changed since the
            # step was created
            step.resolutions = resolutions
        self.add_step(step)
