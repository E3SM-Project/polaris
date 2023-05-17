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

        self.add_input_file(
           filename='mesh.nc',
           target='../base_mesh/mesh.nc')
        self.add_input_file(
           filename='graph.info',
           target='../base_mesh/graph.info')
        self.add_output_file('initial_state.nc')

    def run(self):
        """
        Run this step of the test case
        """
        config = self.config

        dsMesh = xr.open_dataset('mesh.nc')

        ds = dsMesh.copy()
        x_cell = ds.xCell

        bottom_depth = config.getfloat('vertical_grid', 'bottom_depth')

        ds['bottomDepth'] = bottom_depth * xr.ones_like(x_cell)
        ds['ssh'] = xr.zeros_like(x_cell)

        init_vertical_coord(config, ds)

        # resolution = self.resolution
        section = config['galewsky_jet']
        temperature = section.getfloat('temperature')
        salinity = section.getfloat('salinity')
        # coriolis_parameter = section.getfloat('coriolis_parameter')

        temperature_array = temperature * xr.ones_like(x_cell)
        temperature_array, _ = xr.broadcast(temperature_array, ds.refZMid)
        ds['temperature'] = temperature_array.expand_dims(dim='Time', axis=0)
        ds['salinity'] = salinity * xr.ones_like(ds.temperature)
        # ds['normalVelocity'] = normal_velocity
        # ds['fCell'] = coriolis_parameter * xr.ones_like(x_cell)
        # ds['fEdge'] = coriolis_parameter * xr.ones_like(ds.xEdge)
        # ds['fVertex'] = coriolis_parameter * xr.ones_like(ds.xVertex)

        # ds.attrs['nx'] = nx
        # ds.attrs['ny'] = ny
        # ds.attrs['dc'] = dc

        write_netcdf(ds, 'initial_state.nc')
