import numpy as np
import xarray as xr
from mpas_tools.cime.constants import constants
from mpas_tools.io import write_netcdf
from mpas_tools.mesh.conversion import convert, cull
from mpas_tools.planar_hex import make_planar_hex_mesh

from polaris.ocean.eos import compute_specvol
from polaris.ocean.model import OceanIOStep
from polaris.ocean.vertical import init_vertical_coord
from polaris.ocean.vertical.ztilde import (
    geom_height_from_pseudo_height,
    pressure_from_z_tilde,
)
from polaris.resolution import resolution_to_string
from polaris.tasks.ocean.two_column.column import get_array_from_mid_grad


class Init(OceanIOStep):
    """
    A step for creating a mesh and initial condition for two column
    test cases

    Attributes
    ----------
    resolution : float
        The horizontal resolution in km
    """

    def __init__(self, component, resolution, indir):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        resolution : float
            The horizontal resolution in km

        indir : str
            The subdirectory that the task belongs to, that this step will
            go into a subdirectory of
        """
        self.resolution = resolution
        name = f'init_{resolution_to_string(resolution)}'
        super().__init__(component=component, name=name, indir=indir)
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
        # logger.setLevel(logging.INFO)
        config = self.config
        if config.get('ocean', 'model') != 'omega':
            raise ValueError(
                'The two_column test case is only supported for the '
                'Omega ocean model.'
            )

        resolution = self.resolution
        rho0 = config.getfloat('vertical_grid', 'rho0')
        assert rho0 is not None, (
            'The "rho0" configuration option must be set in the '
            '"vertical_grid" section.'
        )

        nx = 2
        ny = 2
        dc = 1e3 * resolution
        dx = 1e3 * resolution
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

        ncells = ds_mesh.sizes['nCells']
        if ncells != 2:
            raise ValueError(
                'The two-column test case requires a mesh with exactly '
                f'2 cells, but the culled mesh has '
                f'{ncells} cells.'
            )

        x = resolution * np.array([-0.5, 0.5], dtype=float)
        geom_ssh, geom_z_bot = self._get_geom_ssh_z_bot(x)

        goal_geom_water_column_thickness = geom_ssh - geom_z_bot

        # first guess at the pseudo bottom depth is the geometric
        # water column thickness
        pseudo_bottom_depth = goal_geom_water_column_thickness

        water_col_adjust_iter_count = config.getint(
            'two_column', 'water_col_adjust_iter_count'
        )

        if water_col_adjust_iter_count is None:
            raise ValueError(
                'The "water_col_adjust_iter_count" configuration option '
                'must be set in the "two_column" section.'
            )

        for iter in range(water_col_adjust_iter_count):
            ds = self._init_z_tilde_vert_coord(ds_mesh, pseudo_bottom_depth)

            z_tilde_mid = ds.zMid
            h_tilde = ds.layerThickness

            logger.debug(f'z_tilde_mid = {z_tilde_mid}')
            logger.debug(f'h_tilde = {h_tilde}')

            ct, sa = self._interpolate_t_s(
                ds=ds,
                z_tilde_mid=z_tilde_mid,
                x=x,
                rho0=rho0,
            )
            p_mid = pressure_from_z_tilde(
                z_tilde=z_tilde_mid,
                rho0=rho0,
            )

            logger.debug(f'ct = {ct}')
            logger.debug(f'sa = {sa}')
            logger.debug(f'p_mid = {p_mid}')

            spec_vol = compute_specvol(
                config=config,
                temperature=ct,
                salinity=sa,
                pressure=p_mid,
            )

            logger.debug(f'geom_z_bot = {geom_z_bot}')
            logger.debug(f'spec_vol = {spec_vol}')

            min_level_cell = ds.minLevelCell - 1
            max_level_cell = ds.maxLevelCell - 1
            logger.debug(f'min_level_cell = {min_level_cell}')
            logger.debug(f'max_level_cell = {max_level_cell}')

            geom_z_inter, geom_z_mid = geom_height_from_pseudo_height(
                geom_z_bot=geom_z_bot,
                h_tilde=h_tilde,
                spec_vol=spec_vol,
                min_level_cell=min_level_cell,
                max_level_cell=max_level_cell,
                rho0=rho0,
            )

            logger.debug(f'geom_z_inter = {geom_z_inter}')
            logger.debug(f'geom_z_mid = {geom_z_mid}')

            # the water column thickness is the difference in the geometric
            # height between the first and last valid valid interfaces

            geom_z_min = geom_z_inter.isel(
                Time=0, nVertLevelsP1=min_level_cell
            )
            geom_z_max = geom_z_inter.isel(
                Time=0, nVertLevelsP1=max_level_cell + 1
            )
            # the min is shallower (less negative) than the max
            geom_water_column_thickness = geom_z_min - geom_z_max
            logger.debug(
                f'geom_water_column_thickness = {geom_water_column_thickness}'
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

        ds['temperature'] = ct
        ds['salinity'] = sa
        ds['SpecVol'] = spec_vol

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

        self._compute_montgomery_and_hpga(ds=ds, rho0=rho0, dx=dx, p_mid=p_mid)

        ds.layerThickness.attrs['long_name'] = 'pseudo-layer thickness'
        ds.layerThickness.attrs['units'] = 'm'

        ds.zMid.attrs['long_name'] = 'pseudo-height at layer midpoints'
        ds.zMid.attrs['units'] = 'm'

        nedges = ds_mesh.sizes['nEdges']
        nvertlevels = ds.sizes['nVertLevels']

        ds['normalVelocity'] = xr.DataArray(
            data=np.zeros((1, nedges, nvertlevels), dtype=float),
            dims=['Time', 'nEdges', 'nVertLevels'],
            attrs={
                'long_name': 'normal velocity',
                'units': 'm s-1',
            },
        )
        ds['fCell'] = xr.zeros_like(ds_mesh.xCell)
        ds['fEdge'] = xr.zeros_like(ds_mesh.xEdge)
        ds['fVertex'] = xr.zeros_like(ds_mesh.xVertex)

        ds.attrs['nx'] = nx
        ds.attrs['ny'] = ny
        ds.attrs['dc'] = dc
        self.write_model_dataset(ds, 'initial_state.nc')

    def _compute_montgomery_and_hpga(
        self,
        ds: xr.Dataset,
        rho0: float,
        dx: float,
        p_mid: xr.DataArray,
    ) -> None:
        """Compute Montgomery potential and a 2-column HPGA.

        This mimics the way Omega will compute the horizontal pressure
        gradient: simple finite differences between the two columns.

        The along-column HPGA is computed as:

            HPGA = dM/dx - p_edge * d(alpha)/dx

        where M is the Montgomery potential, alpha is the specific volume,
        and p_edge is the pressure averaged between the two columns.

        Outputs are added to ``ds``:
        - MontgomeryMid (Time, nCells, nVertLevels)
        - MontgomeryInter (Time, nCells, nVertLevels, nbnds)
        - HPGAMid (Time, nVertLevels)
        - HPGAInter (Time, nVertLevels, nbnds)
        """

        if ds.sizes.get('nCells', 0) != 2:
            raise ValueError(
                'The two-column HPGA computation requires exactly 2 cells.'
            )
        if dx == 0.0:
            raise ValueError('dx must be non-zero for finite differences.')

        g = constants['SHR_CONST_G']

        # Midpoint quantities (alpha is layerwise constant)
        alpha_mid = ds.SpecVol

        # Interface quantities: Omega treats alpha as constant within each
        # layer, so interface values are represented as bounds for each layer
        # (top and bottom), with discontinuities permitted between layers.
        z_tilde_top = ds.zInterface.isel(nVertLevelsP1=slice(0, -1)).rename(
            {'nVertLevelsP1': 'nVertLevels'}
        )
        z_tilde_bot = ds.zInterface.isel(nVertLevelsP1=slice(1, None)).rename(
            {'nVertLevelsP1': 'nVertLevels'}
        )
        z_top = ds.GeomZInter.isel(nVertLevelsP1=slice(0, -1)).rename(
            {'nVertLevelsP1': 'nVertLevels'}
        )
        z_bot = ds.GeomZInter.isel(nVertLevelsP1=slice(1, None)).rename(
            {'nVertLevelsP1': 'nVertLevels'}
        )

        z_tilde_bnds = xr.concat([z_tilde_top, z_tilde_bot], dim='nbnds')
        z_bnds = xr.concat([z_top, z_bot], dim='nbnds')
        # put nbnds last for readability/consistency
        z_tilde_bnds = z_tilde_bnds.transpose(
            'Time', 'nCells', 'nVertLevels', 'nbnds'
        )
        z_bnds = z_bnds.transpose('Time', 'nCells', 'nVertLevels', 'nbnds')

        alpha_bnds = alpha_mid.expand_dims(nbnds=[0, 1]).transpose(
            'Time', 'nCells', 'nVertLevels', 'nbnds'
        )
        montgomery_inter = g * (rho0 * alpha_bnds * z_tilde_bnds + z_bnds)
        montgomery_inter = montgomery_inter.transpose(
            'Time', 'nCells', 'nVertLevels', 'nbnds'
        )

        # Omega convention: Montgomery potential at midpoints is the mean of
        # the two adjacent interface values.
        montgomery_mid = 0.5 * (
            montgomery_inter.isel(nbnds=0) + montgomery_inter.isel(nbnds=1)
        )

        # 2-column finite differences across the pair
        dM_dx_mid = (
            montgomery_mid.isel(nCells=1) - montgomery_mid.isel(nCells=0)
        ) / dx
        dalpha_dx_mid = (
            alpha_mid.isel(nCells=1) - alpha_mid.isel(nCells=0)
        ) / dx

        dsa_dx_mid = (
            ds.salinity.isel(nCells=1) - ds.salinity.isel(nCells=0)
        ) / dx

        # Pressure (positive downward), averaged to the edge between columns
        p_edge_mid = 0.5 * (p_mid.isel(nCells=0) + p_mid.isel(nCells=1))

        hpga_mid = dM_dx_mid - p_edge_mid * dalpha_dx_mid

        ds['MontgomeryMid'] = montgomery_mid
        ds.MontgomeryMid.attrs['long_name'] = (
            'Montgomery potential at layer midpoints'
        )
        ds.MontgomeryMid.attrs['units'] = 'm2 s-2'

        ds['MontgomeryInter'] = montgomery_inter
        ds.MontgomeryInter.attrs['long_name'] = (
            'Montgomery potential at layer interfaces (bounds)'
        )
        ds.MontgomeryInter.attrs['units'] = 'm2 s-2'

        ds['HPGA'] = hpga_mid
        ds.HPGA.attrs = {
            'long_name': (
                'along-layer pressure gradient acceleration at layer midpoints'
            ),
            'units': 'm s-2',
        }

        ds['dMdxMid'] = dM_dx_mid
        ds.dMdxMid.attrs = {
            'long_name': 'Gradient of Montgomery potential at layer midpoints',
            'units': 'm s-2',
        }

        ds['PEdgeMid'] = p_edge_mid
        ds.PEdgeMid.attrs = {
            'long_name': 'Pressure at horizontal edge and layer midpoints',
            'units': 'Pa',
        }

        ds['dalphadxMid'] = dalpha_dx_mid
        ds.dalphadxMid.attrs = {
            'long_name': 'Gradient of specific volume at layer midpoints',
            'units': 'm2 kg-1',
        }

        ds['dSAdxMid'] = dsa_dx_mid
        ds.dSAdxMid.attrs = {
            'long_name': 'Gradient of absolute salinity at layer midpoints',
            'units': 'g kg-1 m-1',
        }

    def _get_geom_ssh_z_bot(
        self, x: np.ndarray
    ) -> tuple[xr.DataArray, xr.DataArray]:
        """
        Get the geometric sea surface height and sea floor height for each
        column from the configuration.
        """
        config = self.config
        geom_ssh = get_array_from_mid_grad(config, 'geom_ssh', x)
        geom_z_bot = get_array_from_mid_grad(config, 'geom_z_bot', x)
        return (
            xr.DataArray(
                data=geom_ssh,
                dims=['nCells'],
                attrs={
                    'long_name': 'sea surface geometric height',
                    'units': 'm',
                },
            ),
            xr.DataArray(
                data=geom_z_bot,
                dims=['nCells'],
                attrs={
                    'long_name': 'seafloor geometric height',
                    'units': 'm',
                },
            ),
        )

    def _init_z_tilde_vert_coord(
        self, ds_mesh: xr.Dataset, pseudo_bottom_depth: xr.DataArray
    ) -> xr.Dataset:
        """
        Initialize variables for a z-tilde vertical coordinate.
        """
        config = self.config

        ds = ds_mesh.copy()

        ds['bottomDepth'] = pseudo_bottom_depth
        ds.bottomDepth.attrs['long_name'] = 'seafloor pseudo-height'
        ds.bottomDepth.attrs['units'] = 'm'
        # the pseudo-ssh is always zero (like the surface pressure)
        ds['ssh'] = xr.zeros_like(pseudo_bottom_depth)
        ds.ssh.attrs['long_name'] = 'sea surface pseudo-height'
        ds.ssh.attrs['units'] = 'm'
        init_vertical_coord(config, ds)
        return ds

    def _get_z_tilde_t_s_nodes(
        self, x: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Get the z-tilde, temperature and salinity node values from the
        configuration.
        """
        config = self.config
        z_tilde_node = get_array_from_mid_grad(config, 'z_tilde', x)
        t_node = get_array_from_mid_grad(config, 'temperature', x)
        s_node = get_array_from_mid_grad(config, 'salinity', x)

        if (
            z_tilde_node.shape != t_node.shape
            or z_tilde_node.shape != s_node.shape
        ):
            raise ValueError(
                'The number of z_tilde, temperature and salinity '
                'points must be the same in each column.'
            )

        return z_tilde_node, t_node, s_node

    def _interpolate_t_s(
        self,
        ds: xr.Dataset,
        z_tilde_mid: xr.DataArray,
        x: np.ndarray,
        rho0: float,
    ) -> tuple[xr.DataArray, xr.DataArray]:
        """
        Compute temperature, salinity, pressure and specific volume given
        z-tilde
        """

        z_tilde_node, t_node, s_node = self._get_z_tilde_t_s_nodes(x)

        ncells = ds.sizes['nCells']
        nvertlevels = ds.sizes['nVertLevels']

        temperature_np = np.zeros((1, ncells, nvertlevels), dtype=float)
        salinity_np = np.zeros((1, ncells, nvertlevels), dtype=float)

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

        return temperature, salinity
