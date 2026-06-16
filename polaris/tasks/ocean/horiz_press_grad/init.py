import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf
from mpas_tools.mesh.conversion import convert, cull
from mpas_tools.planar_hex import make_planar_hex_mesh

from polaris.ocean.coriolis import add_coriolis_to_dataset
from polaris.ocean.model import OceanIOStep
from polaris.ocean.vertical.pstar import init_pstar_vertical_coord
from polaris.ocean.vertical.pstar_init import PStarInitStep
from polaris.ocean.vertical.ztilde import Gravity, RhoSw
from polaris.resolution import resolution_to_string
from polaris.tasks.ocean.horiz_press_grad.column import (
    get_array_from_mid_grad,
    get_pchip_interpolator,
)


class Init(PStarInitStep, OceanIOStep):
    """
    A step for creating a mesh and initial condition for two column
    test cases

    Attributes
    ----------
    horiz_res : float
        The horizontal resolution in km

    vert_res : float
        The vertical resolution in m

    x : numpy.ndarray
        The x-coordinates of the two columns in km, used by
        :py:meth:`init_tracers` and :py:meth:`_build_pstar_coord_ds`.
    """

    def __init__(self, component, horiz_res, vert_res, indir):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        horiz_res : float
            The horizontal resolution in km

        vert_res : float
            The vertical resolution in m

        indir : str
            The subdirectory that the task belongs to, that this step will
            go into a subdirectory of
        """
        self.horiz_res = horiz_res
        self.vert_res = vert_res
        self.x: np.ndarray = np.array([])
        name = f'init_{resolution_to_string(horiz_res)}'
        super().__init__(component=component, name=name, indir=indir)

    def setup(self):
        super().setup()
        self.add_output_files_for_ocean_model_input(
            horiz_mesh_filename='culled_mesh.nc',
        )

    def run(self):
        """
        Run this step of the test case
        """
        logger = self.logger
        config = self.config
        hpg_section = config['horiz_press_grad']
        if config.get('ocean', 'model') != 'omega':
            raise ValueError(
                'The horiz_press_grad test case is only supported for the '
                'Omega ocean model.'
            )

        horiz_res = self.horiz_res
        vert_res = self.vert_res

        z_tilde_bot_mid = hpg_section.getfloat('z_tilde_bot_mid')

        assert z_tilde_bot_mid is not None, (
            'The "z_tilde_bot_mid" configuration option must be set in the '
            '"horiz_press_grad" section.'
        )

        # it needs to be an error if the full water column can't be evenly
        # divided by the resolution, because the later analysis will fail
        if (-z_tilde_bot_mid / vert_res) % 1 != 0:
            raise ValueError(
                'The "z_tilde_bot_mid" value must be an integer multiple of '
                'the vertical resolution to ensure that the vertical grid can '
                'be evenly divided into layers. Currently, z_tilde_bot_mid = '
                f'{z_tilde_bot_mid} and vert_res = {vert_res}, which results '
                f'in {-z_tilde_bot_mid / vert_res} layers.'
            )
        vert_levels = int(-z_tilde_bot_mid / vert_res)

        config.set('vertical_grid', 'vert_levels', str(vert_levels))

        nx = 2
        ny = 2
        dc = 1e3 * horiz_res
        dx = 1e3 * horiz_res
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
        ds_mesh = add_coriolis_to_dataset(config, ds_mesh)
        self.write_horiz_mesh_dataset(ds_mesh, 'culled_mesh.nc', config)

        ncells = ds_mesh.sizes['nCells']
        if ncells != 2:
            raise ValueError(
                'The two-column test case requires a mesh with exactly '
                f'2 cells, but the culled mesh has '
                f'{ncells} cells.'
            )

        x = horiz_res * np.array([-0.5, 0.5], dtype=float)
        # Store x so init_tracers and _build_pstar_coord_ds can access it
        self.x = x
        geom_ssh, geom_z_bot = self._get_geom_ssh_z_bot(x)

        # Delegate the p-star iterative initialization to the base class.
        # surface_pressure defaults to zero; sea_surface_height drives the
        # target water-column thickness.
        ds = self.run_pstar_init(
            ds_mesh=ds_mesh,
            geom_z_bot=geom_z_bot,
            sea_surface_height=geom_ssh,
        )

        ds['Density'] = 1.0 / ds['SpecVol']
        ds.Density.attrs['long_name'] = 'density'
        ds.Density.attrs['units'] = 'kg m-3'

        nvertlevels = ds.sizes['nVertLevels']
        nedges = ds_mesh.sizes['nEdges']

        ds['normalVelocity'] = xr.DataArray(
            data=np.zeros((1, nedges, nvertlevels), dtype=float),
            dims=['Time', 'nEdges', 'nVertLevels'],
            attrs={
                'long_name': 'normal velocity',
                'units': 'm s-1',
            },
        )
        ds.attrs['nx'] = nx
        ds.attrs['ny'] = ny
        ds.attrs['dc'] = dc

        self._compute_montgomery_and_hpga(ds=ds, dx=dx, p_mid=ds.pressure)

        self.write_vert_coord_dataset(ds, 'vert_coord.nc', config)
        self.write_initial_state_dataset(ds, 'init.nc', config)

    def init_tracers(
        self, ds: xr.Dataset
    ) -> tuple[xr.DataArray, xr.DataArray]:
        """
        Interpolate conservative temperature and absolute salinity from
        piecewise pseudo-height profiles defined in the configuration.
        """
        return self._interpolate_t_s(ds=ds, z_tilde_mid=ds.ZTildeMid, x=self.x)

    def _build_pstar_coord_ds(
        self,
        ds_mesh: xr.Dataset,
        bottom_pressure: xr.DataArray,
        surface_pressure: xr.DataArray | None = None,
    ) -> xr.Dataset:
        """
        Build the p-star coordinate per cell, allowing each column to have a
        different reference pseudo-depth set by ``z_tilde_bot`` in config.
        """
        config = self.config
        x = self.x

        z_tilde_bot = get_array_from_mid_grad(config, 'z_tilde_bot', x)

        ds = ds_mesh.copy()
        ds['BottomPressure'] = bottom_pressure
        ds.BottomPressure.attrs['long_name'] = 'seafloor gauge pressure'
        ds.BottomPressure.attrs['units'] = 'Pa'
        if surface_pressure is None:
            surface_pressure = xr.zeros_like(bottom_pressure)
        ds['SurfacePressure'] = surface_pressure
        ds.SurfacePressure.attrs['long_name'] = 'sea surface gauge pressure'
        ds.SurfacePressure.attrs['units'] = 'Pa'

        ds_list: list[xr.Dataset] = []
        for icell in range(ds.sizes['nCells']):
            pseudo_bottom_depth = -z_tilde_bot[icell]
            ds_cell = ds.isel(nCells=slice(icell, icell + 1))
            local_config = config.copy()
            local_config.set(
                'vertical_grid', 'bottom_depth', str(pseudo_bottom_depth)
            )
            init_pstar_vertical_coord(local_config, ds_cell)
            cell_vars = [
                var
                for var in ds_cell.data_vars
                if 'nCells' in ds_cell[var].dims
            ]
            ds_list.append(ds_cell[cell_vars])

        ds_cell_vars = xr.concat(ds_list, dim='nCells')
        for var in ds_cell_vars.data_vars:
            attrs = ds_cell_vars[var].attrs
            ds[var] = ds_cell_vars[var]
            ds[var].attrs = attrs

        # vertCoordMovementWeights is a vertical-only variable; the per-cell
        # loop above only copies cell variables back, so add it here.
        ds['vertCoordMovementWeights'] = xr.DataArray(
            data=np.ones(ds.sizes['nVertLevels'], dtype=float),
            dims=['nVertLevels'],
            attrs={
                'long_name': 'vertical coordinate movement weights',
                'units': '1',
            },
        )
        return ds

    def _compute_montgomery_and_hpga(
        self,
        ds: xr.Dataset,
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

        # Midpoint quantities (alpha is layerwise constant)
        alpha_mid = ds.SpecVol

        # Interface quantities: Omega treats alpha as constant within each
        # layer, so interface values are represented as bounds for each layer
        # (top and bottom), with discontinuities permitted between layers.
        z_tilde_top = ds.ZTildeInterface.isel(
            nVertLevelsP1=slice(0, -1)
        ).rename({'nVertLevelsP1': 'nVertLevels'})
        z_tilde_bot = ds.ZTildeInterface.isel(
            nVertLevelsP1=slice(1, None)
        ).rename({'nVertLevelsP1': 'nVertLevels'})
        z_top = ds.GeomZInterface.isel(nVertLevelsP1=slice(0, -1)).rename(
            {'nVertLevelsP1': 'nVertLevels'}
        )
        z_bot = ds.GeomZInterface.isel(nVertLevelsP1=slice(1, None)).rename(
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
        # Montgomery: M = alpha * p + g * z, with p = -rho0 * g * z_tilde
        montgomery_inter = Gravity * (
            z_bnds - RhoSw * alpha_bnds * z_tilde_bnds
        )
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

        # Gauge pressure (positive downward), averaged to the edge between
        # columns
        p_edge_mid = 0.5 * (p_mid.isel(nCells=0) + p_mid.isel(nCells=1))

        hpga_mid = -dM_dx_mid + p_edge_mid * dalpha_dx_mid

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
            'long_name': (
                'Gauge pressure at horizontal edge and layer midpoints'
            ),
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
    ) -> tuple[xr.DataArray, xr.DataArray]:
        """
        Interpolate temperature and salinity to p-star layer midpoints using
        piecewise pseudo-height profiles from configuration.
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
            z_tilde_mid_col = z_tilde_mid.isel(Time=0, nCells=icell).values

            if len(z_tilde) < 2:
                raise ValueError(
                    'At least two z_tilde points are required to '
                    'define piecewise linear initial conditions.'
                )

            t_interp = get_pchip_interpolator(
                z_tilde_nodes=z_tilde,
                values_nodes=temperatures,
                name='temperature',
            )
            s_interp = get_pchip_interpolator(
                z_tilde_nodes=z_tilde,
                values_nodes=salinities,
                name='salinity',
            )
            valid = np.isfinite(z_tilde_mid_col)
            temperature_np[0, icell, :] = np.nan
            salinity_np[0, icell, :] = np.nan
            if np.any(valid):
                temperature_np[0, icell, valid] = t_interp(
                    z_tilde_mid_col[valid]
                )
                salinity_np[0, icell, valid] = s_interp(z_tilde_mid_col[valid])

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
