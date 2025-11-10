import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf
from mpas_tools.mesh.conversion import convert, cull
from mpas_tools.planar_hex import make_planar_hex_mesh

from polaris.ocean.eos import compute_specvol
from polaris.ocean.hydrostatic.teos10 import integrate_geometric_height
from polaris.ocean.model import OceanIOStep
from polaris.ocean.vertical import init_vertical_coord
from polaris.ocean.vertical.ztilde import pressure_from_z_tilde


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
        assert resolution is not None, (
            'The "resolution" configuration option must be set in the '
            '"two_column" section.'
        )
        rho0 = config.getfloat('vertical_grid', 'rho0')
        assert rho0 is not None, (
            'The "rho0" configuration option must be set in the '
            '"vertical_grid" section.'
        )

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

        ssh_list = config.getexpression('two_column', 'geom_ssh')
        geom_ssh = xr.DataArray(
            data=np.array(ssh_list, dtype=np.float32),
            dims=['nCells'],
        )

        geom_z_bot_list = config.getexpression('two_column', 'geom_z_bot')
        geom_z_bot = xr.DataArray(
            data=np.array(geom_z_bot_list, dtype=np.float32),
            dims=['nCells'],
        )

        x_cell = ds_mesh.xCell
        goal_geom_water_column_thickness = geom_ssh - geom_z_bot

        # first guess at the pseudo bottom depth is the geometric
        # water column thickness
        pseudo_bottom_depth = goal_geom_water_column_thickness

        water_col_adjust_iter_count = config.getint(
            'two_column', 'water_col_adjust_iter_count'
        )

        for iter in range(water_col_adjust_iter_count):
            ds = self._init_z_tilde_vert_coord(ds_mesh, pseudo_bottom_depth)

            z, spec_vol, ct, sa = self._compute_z_t_s_spec_vol_quadrature(
                ds=ds,
                geom_z_bot=geom_z_bot,
            )

            geom_z_inter = z[:, 0::2]
            geom_z_mid = z[:, 1::2]

            geom_water_column_thickness = (
                geom_z_inter[:, -1] - geom_z_inter[:, 0]
            )

            # scale the pseudo bottom depth proportional to how far off we are
            # in the geometric water column thickness from the goal
            scaling_factor = (
                goal_geom_water_column_thickness / geom_water_column_thickness
            )

            max_scaling_factor = scaling_factor.max().item()
            min_scaling_factor = scaling_factor.min().item()
            logger.info(
                f'Iteration {iter}: min scaling factor = '
                f'{min_scaling_factor:.6f}, '
                f'max scaling factor = {max_scaling_factor:.6f}'
            )

            pseudo_bottom_depth = pseudo_bottom_depth * scaling_factor

            logger.info(
                f'Iteration {iter}: pseudo bottom depths = '
                f'{pseudo_bottom_depth.values}'
            )

        ds['temperature'] = xr.DataArray(
            data=ct[np.newaxis, :, 1::2],
            dims=['Time', 'nCells', 'nVertLevels'],
            attrs={
                'long_name': 'conservative temperature',
                'units': 'degC',
            },
        )
        ds['salinity'] = xr.DataArray(
            data=sa[np.newaxis, :, 1::2],
            dims=['Time', 'nCells', 'nVertLevels'],
            attrs={
                'long_name': 'salinity',
                'units': 'g kg-1',
            },
        )

        ds['SpecVol'] = xr.DataArray(
            data=spec_vol[np.newaxis, :, 1::2],
            dims=['Time', 'nCells', 'nVertLevels'],
            attrs={
                'long_name': 'specific volume',
                'units': 'm3 kg-1',
            },
        )
        ds['Density'] = 1.0 / ds['SpecVol']
        ds.Density.attrs['long_name'] = 'density'
        ds.Density.attrs['units'] = 'kg m-3'

        ds['ZTildeMid'] = ds.zMid
        ds.ZTildeMid.attrs['long_name'] = 'pseudo-height at layer midpoints'
        ds.ZTildeMid.attrs['units'] = 'm'

        ds['GeomZMid'] = geom_z_mid
        ds.GeomZMid.attrs['long_name'] = 'geometric height at layer midpoints'
        ds.GeomZMid.attrs['units'] = 'm'

        ds['GeomZInter'] = geom_z_inter
        ds.GeomZInter.attrs['long_name'] = (
            'geometric height at layer interfaces'
        )
        ds.GeomZInter.attrs['units'] = 'm'

        ds.layerThickness.attrs['long_name'] = 'pseudo-layer thickness'
        ds.layerThickness.attrs['units'] = 'm'

        nedges = ds_mesh.sizes['nEdges']
        nvertlevels = ds.sizes['nVertLevels']

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

    def _init_z_tilde_vert_coord(
        self, ds_mesh: xr.Dataset, pseudo_bottom_depth: xr.DataArray
    ) -> xr.Dataset:
        """
        Initialize variables for a z-tilde vertical coordinate.
        """
        config = self.config

        ds = ds_mesh.copy()

        ds['bottomDepth'] = pseudo_bottom_depth
        # the pseudo-ssh is always zero (like the surface pressure)
        ds['ssh'] = xr.zeros_like(pseudo_bottom_depth)
        init_vertical_coord(config, ds)
        return ds

    def _get_z_tilde_t_s_nodes(
        self,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Get the z-tilde, temperature and salinity node values from the
        configuration.
        """

        config = self.config

        lists = {}
        for name in ['z_tilde', 'temperatures', 'salinities']:
            lists[name] = config.getexpression('two_column', name)
            if not isinstance(lists[name], list):
                raise ValueError(
                    f'The "{name}" configuration option must be a list of '
                    f'lists, one per column.'
                )

        z_tilde_node = np.array(lists['z_tilde'], dtype=np.float32)
        t_node = np.array(lists['temperatures'], dtype=np.float32)
        s_node = np.array(lists['salinities'], dtype=np.float32)

        if (
            z_tilde_node.shape != t_node.shape
            or z_tilde_node.shape != s_node.shape
        ):
            raise ValueError(
                'The number of z_tilde, temperature and salinity '
                'points must be the same in each column.'
            )

        return z_tilde_node, t_node, s_node

    def _compute_z_t_s_spec_vol_quadrature(
        self,
        ds: xr.Dataset,
        geom_z_bot: xr.DataArray,
    ):
        """
        Compute temperature, salinity, pressure and specific volume at
        quadrature points (layer interfaces and layer midpoints) given z-tilde
        """
        config = self.config
        rho0 = config.getfloat('vertical_grid', 'rho0')
        ncells = ds.sizes['nCells']
        nvertlevels = ds.sizes['nVertLevels']
        z_tilde_inter = ds.zInterface
        z_tilde_mid = ds.zMid
        z_tilde_node, t_node, s_node = self._get_z_tilde_t_s_nodes()

        z = np.nan * np.ones((ncells, 2 * nvertlevels + 1), dtype=np.float32)
        spec_vol = np.nan * np.ones(
            (ncells, 2 * nvertlevels), dtype=np.float32
        )
        ct = np.nan * np.ones((ncells, 2 * nvertlevels), dtype=np.float32)
        sa = np.nan * np.ones((ncells, 2 * nvertlevels), dtype=np.float32)

        for icell in range(ncells):
            min_level_cell = ds.minLevelCell.isel(nCells=icell).item() - 1
            max_level_cell = ds.maxLevelCell.isel(nCells=icell).item() - 1

            # both interfaces and midpoints
            z_tilde = np.zeros(2 * nvertlevels + 1, dtype=np.float32)
            z_tilde[0::2] = z_tilde_inter.isel(nCells=icell).values
            z_tilde[1::2] = z_tilde_mid.isel(nCells=icell).values
            indices = np.arange(2 * min_level_cell, 2 * max_level_cell + 2)

            z_loc, spec_vol_loc, ct_loc, sa_loc = integrate_geometric_height(
                z_tilde_interfaces=z_tilde[indices],
                z_tilde_nodes=z_tilde_node[icell, :],
                sa_nodes=s_node[icell, :],
                ct_nodes=t_node[icell, :],
                bottom_depth=-geom_z_bot.isel(nCells=icell).items(),
                rho0=rho0,
                method='gauss4',
                subdivisions=2,
            )
            z[icell, indices] = z_loc
            spec_vol[icell, indices] = spec_vol_loc
            ct[icell, indices] = ct_loc
            sa[icell, indices] = sa_loc

        return z, spec_vol, ct, sa

    def _compute_t_s_spec_vol(
        self, ds: xr.Dataset, z_tilde_mid: xr.DataArray
    ) -> tuple[xr.DataArray, xr.DataArray, xr.DataArray, xr.DataArray]:
        """
        Compute temperature, salinity, pressure and specific volume given
        z-tilde
        """

        z_tilde_node, t_node, s_node = self._get_z_tilde_t_s_nodes()

        config = self.config
        ncells = ds.sizes['nCells']
        nvertlevels = ds.sizes['nVertLevels']

        rho0 = config.getfloat('vertical_grid', 'rho0')

        p_mid = pressure_from_z_tilde(
            z_tilde=z_tilde_mid,
            rho0=rho0,
        )

        temperature_np = np.zeros((1, ncells, nvertlevels), dtype=np.float32)
        salinity_np = np.zeros((1, ncells, nvertlevels), dtype=np.float32)

        if z_tilde_node.shape[0] != ncells:
            raise ValueError(
                'The number of z_tilde columns provided must match the '
                'number of mesh columns.'
            )
        if t_node.shape[0] != ncells:
            raise ValueError(
                'The number of temperature columns provided must match the '
                'number of mesh columns.'
            )
        if s_node.shape[0] != ncells:
            raise ValueError(
                'The number of salinity columns provided must match the '
                'number of mesh columns.'
            )

        for icell in range(ncells):
            z_tilde = z_tilde_node[icell, :]
            temperatures = t_node[icell, :]
            salinities = s_node[icell, :]
            z_mid = z_tilde_mid.isel(nCells=icell).values

            if len(z_tilde) < 2:
                raise ValueError(
                    'At least two z_tilde points are required to '
                    'define piecewise linear initial conditions.'
                )

            temperature_np[0, icell, :] = np.interp(
                -z_mid, -z_tilde, temperatures
            )
            salinity_np[0, icell, :] = np.interp(-z_mid, -z_tilde, salinities)

        temperature = xr.DataArray(
            data=temperature_np,
            dims=['Time', 'nCells', 'nVertLevels'],
            attrs={
                'long_name': 'conservative temperature',
                'units': 'degC',
            },
        )
        salinity = xr.DataArray(
            data=salinity_np,
            dims=['Time', 'nCells', 'nVertLevels'],
            attrs={
                'long_name': 'absolute salinity',
                'units': 'g kg-1',
            },
        )

        spec_vol = compute_specvol(
            config=config,
            temperature=temperature,
            salinity=salinity,
            pressure=p_mid,
        )
        return temperature, salinity, p_mid, spec_vol
