import cmocean  # noqa: F401
import xarray as xr
from mpas_tools.io import write_netcdf
from mpas_tools.mesh.jet import init as jet_init

from polaris import Step
from polaris.ocean.vertical import init_vertical_coord


class InitialState(Step):
    """
    A step for creating a mesh and initial condition
    for galewsky jet barotropic instability
    test case

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
        # self.add_input_file(
        #     filename='init.nc')
        self.add_output_file('initial_state.nc')

    def run(self):
        """
        Run this step of the test case
        """
        config = self.config
# update rsph from cime.constants
        # jet_init(name='mesh.nc', save='velocity_ic.nc',
        #         rsph=6371220.0, pert=False)
        # ds2 = xr.open_dataset('velocity_ic.nc')

        dsMesh = xr.open_dataset('mesh.nc')

        ds = dsMesh.copy()
        x_cell = ds.xCell

        bottom_depth = config.getfloat('vertical_grid', 'bottom_depth')

        ds['bottomDepth'] = bottom_depth * xr.ones_like(x_cell)
        ds['ssh'] = xr.zeros_like(x_cell)
        # ds['ssh'] = ds2.h - ds['bottomDepth']

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

        # ds2 = xr.open_dataset('init.nc')
        jet_init(name='mesh.nc', save='velocity_ic.nc',
                 rsph=6371220.0, pert=True)
        ds2 = xr.open_dataset('velocity_ic.nc')

        unrm_array, _ = xr.broadcast(ds2.u, ds.refZMid)
        ds['normalVelocity'] = unrm_array
        # ds['normalVelocity'] = ds2.u
        h_array, _ = xr.broadcast(ds2.h, ds.refZMid)
        ds['layerThickness'] = h_array
        ds['fCell'] = ds2.fCell
        ds['fEdge'] = ds2.fEdge
        ds['fVertex'] = ds2.fVertex
        ds['ssh'] = ds2.h - ds['bottomDepth']

        # if (config.getfloat('vertical_grid', 'grid_type') == 'uniform'):
        # nlev = config.getfloat('vertical_grid', 'vert_levels')
        # ds['layerThickness'], _ = xr.broadcast(ds2.h / nlev, ds.refZMid)

        write_netcdf(ds, 'initial_state.nc')
