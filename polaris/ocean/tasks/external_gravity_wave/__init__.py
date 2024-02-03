from typing import Dict

from polaris import Step, Task
from polaris.config import PolarisConfigParser
from polaris.ocean.mesh.spherical import add_spherical_base_mesh_step
from polaris.ocean.tasks.external_gravity_wave.analysis import Analysis
from polaris.ocean.tasks.external_gravity_wave.forward import Forward
from polaris.ocean.tasks.external_gravity_wave.init import Init
from polaris.ocean.tasks.external_gravity_wave.lts_regions import LTSRegions


def add_external_gravity_wave_tasks(component):
    """
    Add tasks that define variants of the external gravity wave test case

    component : polaris.ocean.Ocean
        the ocean component that the tasks will be added to
    """

    for icosahedral, prefix in [(True, 'icos'), (False, 'qu')]:
        for use_lts in [True, False]:

            egw = 'ext_grav_wav'
            if use_lts:
                filepath = (f'spherical/{prefix}/{egw}_local_time_step/'
                            'ext_grav_wav_local_time_step.cfg')
            else:
                filepath = (f'spherical/{prefix}/{egw}_global_time_step/'
                            'ext_grav_wav_global_time_step.cfg')
            config = PolarisConfigParser(filepath=filepath)
            config.add_from_package('polaris.ocean.convergence',
                                    'convergence.cfg')
            if use_lts:
                config.add_from_package(('polaris.ocean.tasks.'
                                        'external_gravity_wave'),
                                        'ext_grav_wav_local_time_step.cfg')
            else:
                config.add_from_package(('polaris.ocean.tasks.'
                                        'external_gravity_wave'),
                                        'ext_grav_wav_global_time_step.cfg')

            component.add_task(ExternalGravityWave(component=component,
                                                   config=config,
                                                   icosahedral=icosahedral,
                                                   use_lts=use_lts))


class ExternalGravityWave(Task):
    """
    A simple external gravity wave on an aquaplanet

    Attributes
    ----------
    resolution : float
        Mesh resolution

    icosahedral : bool
        Whether to use icosahedral, as opposed to less regular, JIGSAW meshes

    use_lts : bool
        Whether local time stepping is to be used

    """
    def __init__(self, component, config, icosahedral, use_lts):
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

        use_lts : bool
            Whether local time stepping is to be used
        """
        if icosahedral:
            prefix = 'icos'
        else:
            prefix = 'qu'

        subdir = f'spherical/{prefix}/ext_grav_wav'
        name = f'{prefix}_ext_grav_wav'
        if use_lts:
            subdir += '_local_time_step'
            name += '_local_time_step'
        else:
            subdir += '_global_time_step'
            name += '_global_time_step'
        link = None

        super().__init__(component=component, name=name, subdir=subdir)
        self.icosahedral = icosahedral
        self.resolution = None
        self.use_lts = use_lts

        self.set_shared_config(config, link=link)

        self._setup_steps()

    def configure(self):
        """
        Set config options for the test case
        """
        super().configure()

        # set up the steps again in case a user has provided new resolutions
        self._setup_steps()

    def _setup_steps(self):  # noqa: C901
        """ setup steps given resolutions """
        icosahedral = self.icosahedral
        use_lts = self.use_lts
        config = self.config
        config_filename = self.config_filename

        if icosahedral:
            prefix = 'icos'
        else:
            prefix = 'qu'

        section = config['mesh']
        resolution = section.getfloat(f'{prefix}_resolution')

        dts = config.getlist('convergence_forward',
                             'dt', dtype=float)

        if self.resolution == resolution:
            return

        # start fresh with no steps
        for step in list(self.steps.values()):
            self.remove_step(step)

        self.resolution = resolution

        component = self.component

        analysis_dependencies: Dict[str, Dict[str, Step]] = (
            dict(mesh=dict(), init=dict(), forward=dict()))
        base_mesh_step, mesh_name = add_spherical_base_mesh_step(
            component, resolution, icosahedral)
        self.add_step(base_mesh_step, symlink=f'base_mesh/{mesh_name}')
        analysis_dependencies['mesh'][resolution] = base_mesh_step

        ext_grav_wave_dir = f'spherical/{prefix}/ext_grav_wav'
        if use_lts:
            ext_grav_wave_dir += '_local_time_step'
        else:
            ext_grav_wave_dir += '_global_time_step'

        name = f'{prefix}_init_{mesh_name}'
        if use_lts:
            name += '_local_time_step'
        else:
            name += 'global_time_step'
        subdir = f'{ext_grav_wave_dir}/init/{mesh_name}'
        symlink = None
        if subdir in component.steps:
            init_step = component.steps[subdir]
        else:
            init_step = Init(component=component, name=name, subdir=subdir,
                             base_mesh=base_mesh_step)
            init_step.set_shared_config(config, link=config_filename)
        self.add_step(init_step, symlink=symlink)
        analysis_dependencies['init'][resolution] = init_step

        if use_lts:
            name = f'{prefix}_init_lts_{mesh_name}_local_time_step'
            subdir = f'{ext_grav_wave_dir}/init_lts/{mesh_name}'
            symlink = None
            if subdir in component.steps:
                lts_step = component.steps[subdir]
            else:
                lts_step = LTSRegions(component, init_step,
                                      name=name, subdir=subdir)
                lts_step.set_shared_config(config, link=config_filename)

            self.add_step(lts_step, symlink=symlink)
            if use_lts:
                init_step = lts_step

        name = f'{prefix}_forward_{mesh_name}'
        graph_path = None
        if use_lts:
            name += '_local_time_step'
            yaml_filename = 'forward_local_time_step.yaml'
            graph_path = f'ocean/{ext_grav_wave_dir}/init_lts/{mesh_name}'
        else:
            name += '_global_time_step'
            yaml_filename = 'forward_global_time_step.yaml'
        subdir = f'{ext_grav_wave_dir}/forward/{mesh_name}'
        for dt in dts:
            subdir = f'{ext_grav_wave_dir}/forward/{mesh_name}/{int(dt)}s'
            symlink = None
            if subdir in component.steps:
                forward_step = component.steps[subdir]
            else:
                name += f'{int(dt)}' + 's'
                forward_step = Forward(component=component,
                                       name=name, subdir=subdir,
                                       resolution=resolution,
                                       dt=dt, mesh=base_mesh_step,
                                       init=init_step,
                                       graph_path=graph_path,
                                       yaml_filename=yaml_filename)
                forward_step.set_shared_config(config,
                                               link=config_filename)
                self.add_step(forward_step, symlink=symlink)
            analysis_dependencies['forward'][dt] = forward_step

        egw = 'ext_grav_wav'
        if use_lts:
            subdir = f'spherical/{prefix}/{egw}_local_time_step/analysis'
        else:
            subdir = f'spherical/{prefix}/{egw}_global_time_step/analysis'
        symlink = None
        if subdir in component.steps:
            step = component.steps[subdir]
            step.resolution = resolution
            step.dependencies_dict = analysis_dependencies
        else:
            step = Analysis(component=component, resolution=resolution,
                            subdir=subdir,
                            dependencies=analysis_dependencies, dts=dts)
            step.set_shared_config(config, link=config_filename)
        self.add_step(step, symlink=symlink)
