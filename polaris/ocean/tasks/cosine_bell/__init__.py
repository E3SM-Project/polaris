from typing import Dict

from polaris import Step, Task
from polaris.config import PolarisConfigParser
from polaris.ocean.mesh.spherical import add_spherical_base_mesh_step
from polaris.ocean.tasks.cosine_bell.analysis import Analysis
from polaris.ocean.tasks.cosine_bell.forward import Forward
from polaris.ocean.tasks.cosine_bell.init import Init
from polaris.ocean.tasks.cosine_bell.viz import Viz


def add_cosine_bell_tasks(component):
    """
    Add tasks that define variants of the cosine bell test case

    component : polaris.ocean.Ocean
        the ocean component that the tasks will be added to
    """

    for icosahedral, prefix in [(True, 'icos'), (False, 'qu')]:

        filepath = f'spherical/{prefix}/cosine_bell/cosine_bell.cfg'
        config = PolarisConfigParser(filepath=filepath)
        config.add_from_package('polaris.ocean.convergence',
                                'convergence.cfg')
        config.add_from_package('polaris.ocean.convergence.spherical',
                                'spherical.cfg')
        config.add_from_package('polaris.ocean.tasks.cosine_bell',
                                'cosine_bell.cfg')

        for include_viz in [False, True]:
            component.add_task(CosineBell(component=component,
                                          config=config,
                                          icosahedral=icosahedral,
                                          include_viz=include_viz))


class CosineBell(Task):
    """
    A convergence test for the advection of a cosine-bell tracer

    Attributes
    ----------
    resolutions : list of float
        A list of mesh resolutions

    icosahedral : bool
        Whether to use icosahedral, as opposed to less regular, JIGSAW meshes

    include_viz : bool
        Include VizMap and Viz steps for each resolution
    """
    def __init__(self, component, config, icosahedral, include_viz):
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

        include_viz : bool
            Include VizMap and Viz steps for each resolution
        """
        if icosahedral:
            prefix = 'icos'
        else:
            prefix = 'qu'

        subdir = f'spherical/{prefix}/cosine_bell'
        name = f'{prefix}_cosine_bell'
        if include_viz:
            subdir = f'{subdir}/with_viz'
            name = f'{name}_with_viz'
            link = 'cosine_bell.cfg'
        else:
            # config options live in the task already so no need for a symlink
            link = None
        super().__init__(component=component, name=name, subdir=subdir)
        self.resolutions = list()
        self.icosahedral = icosahedral
        self.include_viz = include_viz

        self.set_shared_config(config, link=link)

        self._setup_steps()

    def configure(self):
        """
        Set config options for the test case
        """
        super().configure()

        # set up the steps again in case a user has provided new resolutions
        self._setup_steps()

    def _setup_steps(self):
        """ setup steps given resolutions """
        icosahedral = self.icosahedral
        config = self.config
        config_filename = self.config_filename

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

            cos_bell_dir = f'spherical/{prefix}/cosine_bell'

            name = f'{prefix}_init_{mesh_name}'
            subdir = f'{cos_bell_dir}/init/{mesh_name}'
            if self.include_viz:
                symlink = f'init/{mesh_name}'
            else:
                symlink = None
            if subdir in component.steps:
                init_step = component.steps[subdir]
            else:
                init_step = Init(component=component, name=name, subdir=subdir,
                                 base_mesh=base_mesh_step)
                init_step.set_shared_config(config, link=config_filename)
            self.add_step(init_step, symlink=symlink)
            analysis_dependencies['init'][resolution] = init_step

            name = f'{prefix}_forward_{mesh_name}'
            subdir = f'{cos_bell_dir}/forward/{mesh_name}'
            if self.include_viz:
                symlink = f'forward/{mesh_name}'
            else:
                symlink = None
            if subdir in component.steps:
                forward_step = component.steps[subdir]
            else:
                forward_step = Forward(component=component, name=name,
                                       subdir=subdir, resolution=resolution,
                                       mesh=base_mesh_step,
                                       init=init_step)
                forward_step.set_shared_config(config, link=config_filename)
            self.add_step(forward_step, symlink=symlink)
            analysis_dependencies['forward'][resolution] = forward_step

            if self.include_viz:
                with_viz_dir = f'spherical/{prefix}/cosine_bell/with_viz'
                name = f'{prefix}_viz_{mesh_name}'
                subdir = f'{with_viz_dir}/viz/{mesh_name}'
                step = Viz(component=component, name=name,
                           subdir=subdir, base_mesh=base_mesh_step,
                           init=init_step, forward=forward_step,
                           mesh_name=mesh_name)
                step.set_shared_config(config, link=config_filename)
                self.add_step(step)

        subdir = f'spherical/{prefix}/cosine_bell/analysis'
        if self.include_viz:
            symlink = 'analysis'
        else:
            symlink = None
        if subdir in component.steps:
            step = component.steps[subdir]
            step.resolutions = resolutions
            step.dependencies_dict = analysis_dependencies
        else:
            step = Analysis(component=component, resolutions=resolutions,
                            subdir=subdir,
                            dependencies=analysis_dependencies)
            step.set_shared_config(config, link=config_filename)
        self.add_step(step, symlink=symlink)
