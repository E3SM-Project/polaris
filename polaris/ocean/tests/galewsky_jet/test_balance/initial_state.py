import cmocean  # noqa: F401
import xarray as xr
from mpas_tools.io import write_netcdf
from mpas_tools.mesh.conversion import convert, cull

from polaris import Step
from polaris.ocean.vertical import init_vertical_coord


class InitialState(Step):
    """
    A step for creating a mesh and initial condition for baroclinic channel
    test cases

    Attributes
    ----------
    resolution : float
        The resolution of the test case in km
    """
    def __init__(self, test_case, resolution):
        """
        Create the step

        Parameters
        ----------
        test_case : polaris.TestCase
            The test case this step belongs to

        resolution : float
            The resolution of the test case in km
        """
        super().__init__(test_case=test_case, name='initial_state')
        self.resolution = resolution

        for file in ['base_mesh.nc', 'culled_mesh.nc', 'culled_graph.info',
                     'initial_state.nc']:
            self.add_output_file(file)

    def run(self):
        """
        Run this step of the test case
        """
        # TODO: needs to be cleaned!!!
        config = self.config
        logger = self.logger

        section = config['galewsky_jet']
        resolution = self.resolution

        lx = section.getfloat('lx')
        ly = section.getfloat('ly')

        # these could be hard-coded as functions of specific supported
        # resolutions but it is preferable to make them algorithmic like here
        # for greater flexibility
        # nx, ny = compute_planar_hex_nx_ny(lx, ly, resolution)
        # dc = 1e3 * resolution

        # ds_mesh = make_planar_hex_mesh(nx=nx, ny=ny, dc=dc,
        #                               nonperiodic_x=False,
        #                               nonperiodic_y=True)
        # self.add_step(IcosahedralMeshStep(
        #    test_case=self, name=name, subdir=subdir,
        #    cell_width=resolution))
        write_netcdf(ds_mesh, 'base_mesh.nc')

        ds_mesh = cull(ds_mesh, logger=logger)
        ds_mesh = convert(ds_mesh, graphInfoFileName='culled_graph.info',
                          logger=logger)
        write_netcdf(ds_mesh, 'culled_mesh.nc')

        # section = config['galewsky_jet']
        # temperature_difference = section.getfloat('temperature_difference')
        # salinity = section.getfloat('salinity')
        # coriolis_parameter = section.getfloat('coriolis_parameter')

        ds = ds_mesh.copy()
        x_cell = ds.xCell
        y_cell = ds.yCell

        bottom_depth = config.getfloat('vertical_grid', 'bottom_depth')

        ds['bottomDepth'] = bottom_depth * xr.ones_like(x_cell)
        ds['ssh'] = xr.zeros_like(x_cell)

        init_vertical_coord(config, ds)

        # ds['temperature'] = temperature
        # ds['salinity'] = salinity * xr.ones_like(temperature)
        # ds['normalVelocity'] = normal_velocity
        # ds['fCell'] = coriolis_parameter * xr.ones_like(x_cell)
        # ds['fEdge'] = coriolis_parameter * xr.ones_like(ds.xEdge)
        # ds['fVertex'] = coriolis_parameter * xr.ones_like(ds.xVertex)

        # ds.attrs['nx'] = nx
        # ds.attrs['ny'] = ny
        # ds.attrs['dc'] = dc

        # write_netcdf(ds, 'initial_state.nc')
