from polaris import Task
from polaris.config import PolarisConfigParser
from polaris.ocean.mesh.spherical import add_spherical_base_mesh_step
from polaris.ocean.tasks.sphere_transport.convergence import (
    Convergence,
    ConvergenceViz,
)
from polaris.ocean.tasks.sphere_transport.forward import Forward
from polaris.ocean.tasks.sphere_transport.init import Init
from polaris.ocean.tasks.sphere_transport.viz import Viz, VizMap
from polaris.ocean.tests.sphere_transport.sphere_transport_test_case import (
    SphereTransportTestCase,
)


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
    resolutions : list of int
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
            subdir = 'spherical/icos/sphere_transport'
        else:
            subdir = 'spherical/qu/sphere_transport'
        if include_viz:
            subdir = f'{subdir}/with_viz'
        super().__init__(component=component, name='sphere_transport',
                         subdir=subdir)
        self.resolutions = list()
        self.icosahedral = icosahedral
        self.case_name = case_name
        self.include_viz = include_viz

        # add the steps with default resolutions so they can be listed
        config = PolarisConfigParser()
        package = 'polaris.ocean.tasks.sphere_transport'
        config.add_from_package(package, f'{case_name}.cfg')
        self._setup_steps(config)

    def configure(self):
        """
        Set config options for the test case
        """
        super().configure()
        config = self.config
        config.add_from_package('polaris.mesh', 'mesh.cfg')

        # set up the steps again in case a user has provided new resolutions
        self._setup_steps(config)

    def _setup_steps(self, config):
        """ setup steps given resolutions """
        if self.icosahedral:
            default_resolutions = '60, 120, 240, 480'
        else:
            default_resolutions = '60, 90, 120, 150, 180, 210, 240'

        # set the default values that a user may change before setup
        config.set('sphere_transport', 'resolutions', default_resolutions,
                   comment='a list of resolutions (km) to test')

        # get the resolutions back, perhaps with values set in the user's
        # config file, which takes priority over what we just set above
        resolutions = config.getlist('sphere_transport', 'resolutions',
                                     dtype=int)

        if self.resolutions == resolutions:
            return

        # start fresh with no steps
        for step in list(self.steps.values()):
            self.remove_step(step)

        self.resolutions = resolutions

        component = self.component
        icosahedral = self.icosahedral
        case_name = self.case_name
        if icosahedral:
            prefix = 'icos'
        else:
            prefix = 'qu'

        for resolution in resolutions:
            base_mesh, mesh_name = add_spherical_base_mesh_step(
                component, resolution, icosahedral)
            self.add_step(base_mesh, symlink=f'base_mesh/{mesh_name}')

            sph_trans_dir = f'spherical/{prefix}/sphere_transport/{case_name}'

            name = f'{prefix}_init_{mesh_name}'
            subdir = f'{sph_trans_dir}/init/{mesh_name}'
            if self.include_viz:
                symlink = f'init/{mesh_name}'
            else:
                symlink = None
            if subdir in component.steps:
                step = component.steps[subdir]
            else:
                step = Init(component=component, name=name, subdir=subdir,
                            mesh_name=mesh_name, case_name=case_name)
            self.add_step(step, symlink=symlink)

            name = f'{prefix}_forward_{mesh_name}'
            subdir = f'{sph_trans_dir}/forward/{mesh_name}'
            if self.include_viz:
                symlink = f'forward/{mesh_name}'
            else:
                symlink = None
            if subdir in component.steps:
                step = component.steps[subdir]
            else:
                step = Forward(component=component, name=name,
                               subdir=subdir, resolution=resolution,
                               mesh_name=mesh_name, case_name=case_name)
            self.add_step(step, symlink=symlink)

            if self.include_viz:
                with_viz_dir = f'spherical/{prefix}/sphere_transport/with_viz'

                name = f'{prefix}_map_{mesh_name}'
                subdir = f'{with_viz_dir}/map/{mesh_name}'
                viz_map = VizMap(component=component, name=name,
                                 subdir=subdir, mesh_name=mesh_name)
                self.add_step(viz_map)

                name = f'{prefix}_viz_{mesh_name}'
                subdir = f'{with_viz_dir}/viz/{mesh_name}'
                step = Viz(component=component, name=name,
                           subdir=subdir, viz_map=viz_map,
                           mesh_name=mesh_name)
                self.add_step(step)

        subdir = f'spherical/{prefix}/sphere_transport/convergence'
        if self.include_viz:
            symlink = 'convergence'
        else:
            symlink = None
        if subdir in component.steps:
            step = component.steps[subdir]
        else:
            convergence = Convergence(component=component, test_case=self,
                                      resolutions=resolutions)
        self.add_step(convergence, symlink=symlink)

        subdir = f'spherical/{prefix}/sphere_transport/convergence'
        if self.include_viz:
            symlink = 'convergence'
        else:
            symlink = None
        if subdir in component.steps:
            step = component.steps[subdir]
        else:
            step = ConvergenceViz(component=component,
                                  test_case=self,
                                  resolutions=resolutions,
                                  convergence=convergence)
        self.add_step(step, symlink=symlink)
