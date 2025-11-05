import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf
from mpas_tools.mesh.conversion import convert, cull
from mpas_tools.planar_hex import make_planar_hex_mesh

from polaris.ocean.eos import compute_specvol
from polaris.ocean.model import OceanIOStep
from polaris.ocean.vertical import init_vertical_coord
from polaris.ocean.vertical.ztilde import pressure_from_z_tilde, z_from_z_tilde


class Init(OceanIOStep):
    """
    A step for creating a mesh and initial condition for two column
    test cases
    """

    def __init__(self, component, indir):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        indir : str
            The subdirectory that the task belongs to, that this step will
            go into a subdirectory of
        """
        super().__init__(component=component, name='init', indir=indir)
        for file in [
            'base_mesh.nc',
            'culled_mesh.nc',
            'culled_graph.info',
            'initial_state.nc',
        ]:
            self.add_output_file(file)

    def run(self):
        """
        Run this step of the test case
        """
        logger = self.logger
        config = self.config
        if config.get('ocean', 'model') != 'omega':
            raise ValueError(
                'The two_column test case is only supported for the '
                'Omega ocean model.'
            )

        section = config['two_column']
        resolution = section.getfloat('resolution')
        nx = 2
        ny = 2
        dc = 1e3 * resolution
        ds_mesh = make_planar_hex_mesh(
            nx=nx, ny=ny, dc=dc, nonperiodic_x=True, nonperiodic_y=True
        )

        # cull one more row of cells so we're only left with 2
        cull_cell = ds_mesh.cullCell.values
        ncells = ds_mesh.sizes['nCells']
        # remove the last 2 rows in y
        cull_cell[ncells - 2 * (nx + 2) : ncells + 1] = 1
        ds_mesh['cullCell'] = xr.DataArray(data=cull_cell, dims=['nCells'])

        write_netcdf(ds_mesh, 'base_mesh.nc')
        ds_mesh = cull(ds_mesh, logger=logger)
        ds_mesh = convert(
            ds_mesh, graphInfoFileName='culled_graph.info', logger=logger
        )
        write_netcdf(ds_mesh, 'culled_mesh.nc')

        if ds_mesh.sizes['nCells'] != 2:
            raise ValueError(
                'The two-column test case requires a mesh with exactly '
                f'2 cells, but the culled mesh has '
                f'{ds_mesh.sizes["nCells"]} cells.'
            )

        ssh_list = config.getexpression('two_column', 'ssh')
        ssh = xr.DataArray(
            data=np.array(ssh_list, dtype=np.float32),
            dims=['nCells'],
        )

        ds = ds_mesh.copy()
        x_cell = ds_mesh.xCell
        bottom_depth = config.getfloat('vertical_grid', 'bottom_depth')
        ds['bottomDepth'] = bottom_depth * xr.ones_like(x_cell)
        ds['ssh'] = ssh
        init_vertical_coord(config, ds)

        rho0 = config.getfloat('z_tilde', 'rho0')

        p_mid = pressure_from_z_tilde(ds.zMid, rho0=rho0)

        ncells = ds.sizes['nCells']
        nedges = ds.sizes['nEdges']
        nvertlevels = ds.sizes['nVertLevels']

        lists = {}
        for name in ['depths', 'temperatures', 'salinities']:
            lists[name] = config.getexpression('two_column', name)
            if not isinstance(lists[name], list):
                raise ValueError(
                    f'The "{name}" configuration option must be a list of '
                    f'lists, one per column.'
                )
            if len(lists[name]) != ncells:
                raise ValueError(
                    f'The "{name}" configuration option must have one entry '
                    f'per column ({ncells} columns in the mesh).'
                )

        temperature = np.zeros((1, ncells, nvertlevels), dtype=np.float32)
        salinity = np.zeros((1, ncells, nvertlevels), dtype=np.float32)

        for icell in range(ncells):
            depths = np.array(lists['depths'][icell])
            temperatures = np.array(lists['temperatures'][icell])
            salinities = np.array(lists['salinities'][icell])
            z_mid = ds.zMid.isel(nCells=icell).values

            if len(depths) < 2:
                raise ValueError(
                    'At least two depth points are required to '
                    'define piecewise linear initial conditions.'
                )

            if len(depths) != len(temperatures) or len(depths) != len(
                salinities
            ):
                raise ValueError(
                    'The number of depth, temperature and salinity '
                    'points must be the same in each column.'
                )

            temperature[0, icell, :] = np.interp(-z_mid, -depths, temperatures)
            salinity[0, icell, :] = np.interp(-z_mid, -depths, salinities)

        ds['temperature'] = xr.DataArray(
            data=temperature,
            dims=['Time', 'nCells', 'nVertLevels'],
            attrs={
                'long_name': 'conservative temperature',
                'units': 'degC',
            },
        )
        ds['salinity'] = xr.DataArray(
            data=salinity,
            dims=['Time', 'nCells', 'nVertLevels'],
            attrs={
                'long_name': 'absolute salinity',
                'units': 'g kg-1',
            },
        )

        ds['PMid'] = p_mid

        spec_vol = compute_specvol(
            config=config,
            temperature=ds.temperature,
            salinity=ds.salinity,
            pressure=ds.PMid,
        )
        ds['SpecVol'] = spec_vol
        ds.SpecVol.attrs['long_name'] = 'specific volume'
        ds.SpecVol.attrs['units'] = 'm3 kg-1'

        z_geom_inter, z_geom_mid = z_from_z_tilde(
            layer_thickness=ds.layerThickness,
            bottom_depth=ds.bottomDepth,
            spec_vol=ds.SpecVol,
            rho0=rho0,
        )

        ds['zGeomMid'] = z_geom_mid
        ds.zGeomMid.attrs['long_name'] = 'geometric height at layer midpoints'
        ds.zGeomMid.attrs['units'] = 'm'

        ds['zGeomInter'] = z_geom_inter
        ds.zGeomInter.attrs['long_name'] = (
            'geometric height at layer interfaces'
        )
        ds.zGeomInter.attrs['units'] = 'm'

        ds['normalVelocity'] = xr.DataArray(
            data=np.zeros((1, nedges, nvertlevels), dtype=np.float32),
            dims=['Time', 'nEdges', 'nVertLevels'],
            attrs={
                'long_name': 'normal velocity',
                'units': 'm s-1',
            },
        )
        ds['fCell'] = xr.zeros_like(x_cell)
        ds['fEdge'] = xr.zeros_like(ds_mesh.xEdge)
        ds['fVertex'] = xr.zeros_like(ds_mesh.xVertex)

        ds.attrs['nx'] = nx
        ds.attrs['ny'] = ny
        ds.attrs['dc'] = dc
        self.write_model_dataset(ds, 'initial_state.nc')
