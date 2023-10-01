from typing import Dict

from polaris import Step, Task
from polaris.config import PolarisConfigParser
from polaris.ocean.mesh.spherical import add_spherical_base_mesh_step
from polaris.ocean.tasks.sphere_transport.analysis import Analysis
from polaris.ocean.tasks.sphere_transport.filament_analysis import (
    FilamentAnalysis,
)
from polaris.ocean.tasks.sphere_transport.forward import Forward
from polaris.ocean.tasks.sphere_transport.init import Init
from polaris.ocean.tasks.sphere_transport.viz import Viz, VizMap


def add_sphere_transport_tasks(component):
    """
    Add tasks that define variants of the cosine bell test case

    component : polaris.ocean.Ocean
        the ocean component that the tasks will be added to
    """

    for case_name in ['rotation_2d', 'nondivergent_2d', 'divergent_2d',
                      'correlated_tracers_2d']:
        for include_viz in [False, True]:
            component.add_task(SphereTransport(
                component=component, case_name=case_name, icosahedral=True,
                include_viz=include_viz))


class SphereTransport(Task):
    """
    A test case for testing properties of tracer advection

    Attributes
    ----------
    resolutions : list of float
        A list of mesh resolutions

    icosahedral : bool
        Whether to use icosahedral, as opposed to less regular, JIGSAW meshes

    include_viz : bool
        Include VizMap and Viz steps for each resolution
    """
    def __init__(self, component, case_name, icosahedral, include_viz):
        """
        Create test case for creating a global MPAS-Ocean mesh

        Parameters
        ----------
        component : polaris.ocean.Ocean
            The ocean component that this task belongs to

        case_name: string
            The name of the case which determines what variant of the
            configuration to use

        icosahedral : bool
            Whether to use icosahedral, as opposed to less regular, JIGSAW
            meshes

        include_viz : bool
            Include VizMap and Viz steps for each resolution
        """
        if icosahedral:
            subdir = f'spherical/icos/{case_name}'
        else:
            subdir = f'spherical/qu/{case_name}'
        if include_viz:
            subdir = f'{subdir}/with_viz'
        super().__init__(component=component, name=case_name,
                         subdir=subdir)
        self.resolutions = list()
        self.icosahedral = icosahedral
        self.case_name = case_name
        self.include_viz = include_viz

        # add the steps with default resolutions so they can be listed
        config = PolarisConfigParser()
        config.add_from_package('polaris.ocean.convergence.spherical',
                                'spherical.cfg')
        self._setup_steps(config)

    def configure(self):
        """
        Set config options for the test case
        """
        super().configure()
        case_name = self.case_name
        config = self.config
        config.add_from_package('polaris.mesh', 'mesh.cfg')
        config.add_from_package('polaris.ocean.convergence.spherical',
                                'spherical.cfg')
        package = 'polaris.ocean.tasks.sphere_transport'
        config.add_from_package(package, 'sphere_transport.cfg')
        config.add_from_package(package, f'{case_name}.cfg')

        # set up the steps again in case a user has provided new resolutions
        self._setup_steps(config)

    def _setup_steps(self, config):
        """ setup steps given resolutions """
        case_name = self.case_name
        icosahedral = self.icosahedral
        if icosahedral:
            prefix = 'icos'
        else:
            prefix = 'qu'

        resolutions = config.getlist('spherical_convergence',
                                     f'{prefix}_resolutions', dtype=float)

        if self.resolutions == resolutions:
            return

        # start fresh with no steps
        for step in list(self.steps.values()):
            self.remove_step(step)

        self.resolutions = resolutions

        component = self.component

        analysis_dependencies: Dict[str, Dict[str, Step]] = (
            dict(mesh=dict(), init=dict(), forward=dict()))
        for resolution in resolutions:
            base_mesh_step, mesh_name = add_spherical_base_mesh_step(
                component, resolution, icosahedral)
            self.add_step(base_mesh_step, symlink=f'base_mesh/{mesh_name}')
            analysis_dependencies['mesh'][resolution] = base_mesh_step

            sph_trans_dir = f'spherical/{prefix}/{case_name}'

            name = f'{prefix}_init_{mesh_name}'
            subdir = f'{sph_trans_dir}/init/{mesh_name}'
            if self.include_viz:
                symlink = f'init/{mesh_name}'
            else:
                symlink = None
            if subdir in component.steps:
                init_step = component.steps[subdir]
            else:
                init_step = Init(component=component, name=name, subdir=subdir,
                                 base_mesh=base_mesh_step, case_name=case_name)
            self.add_step(init_step, symlink=symlink)
            analysis_dependencies['init'][resolution] = init_step

            name = f'{prefix}_forward_{mesh_name}'
            subdir = f'{sph_trans_dir}/forward/{mesh_name}'
            if self.include_viz:
                symlink = f'forward/{mesh_name}'
            else:
                symlink = None
            if subdir in component.steps:
                forward_step = component.steps[subdir]
            else:
                forward_step = Forward(component=component, name=name,
                                       subdir=subdir, resolution=resolution,
                                       base_mesh=base_mesh_step,
                                       init=init_step,
                                       case_name=case_name)
            self.add_step(forward_step, symlink=symlink)
            analysis_dependencies['forward'][resolution] = forward_step

            if self.include_viz:
                with_viz_dir = f'{sph_trans_dir}/with_viz'

                name = f'{prefix}_map_{mesh_name}'
                subdir = f'{with_viz_dir}/map/{mesh_name}'
                viz_map = VizMap(component=component, name=name,
                                 subdir=subdir, base_mesh=base_mesh_step,
                                 mesh_name=mesh_name)
                self.add_step(viz_map)

                name = f'{prefix}_viz_{mesh_name}'
                subdir = f'{with_viz_dir}/viz/{mesh_name}'
                step = Viz(component=component, name=name,
                           subdir=subdir, base_mesh=base_mesh_step,
                           init=init_step, forward=forward_step,
                           viz_map=viz_map, mesh_name=mesh_name)
                self.add_step(step)

        subdir = f'{sph_trans_dir}/analysis'
        if self.include_viz:
            symlink = 'analysis'
        else:
            symlink = None
        if subdir in component.steps:
            step = component.steps[subdir]
        else:
            step = Analysis(component=component, resolutions=resolutions,
                            icosahedral=icosahedral, subdir=subdir,
                            case_name=case_name,
                            dependencies=analysis_dependencies)
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
                                        resolutions=resolutions,
                                        icosahedral=icosahedral, subdir=subdir,
                                        case_name=case_name,
                                        dependencies=analysis_dependencies)
            self.add_step(step, symlink=symlink)
