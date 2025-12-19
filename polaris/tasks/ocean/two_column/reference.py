import numpy as np
import xarray as xr
from mpas_tools.cime.constants import constants

from polaris.ocean.hydrostatic.teos10 import integrate_geometric_height
from polaris.ocean.model import OceanIOStep
from polaris.tasks.ocean.two_column.column import get_array_from_mid_grad


class Reference(OceanIOStep):
    """
    A step for creating a high-fidelity reference solution for two column
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
        name = 'reference'
        super().__init__(component=component, name=name, indir=indir)
        for file in [
            'reference_solution.nc',
        ]:
            self.add_output_file(file)

    def run(self):
        """
        Run this step of the test case
        """
        logger = self.logger
        # logger.setLevel(logging.DEBUG)
        config = self.config
        if config.get('ocean', 'model') != 'omega':
            raise ValueError(
                'The two_column test case is only supported for the '
                'Omega ocean model.'
            )

        resolution = config.getfloat('two_column', 'reference_resolution')
        assert resolution is not None, (
            'The "reference_resolution" configuration option must be set in '
            'the "two_column" section.'
        )
        rho0 = config.getfloat('vertical_grid', 'rho0')
        assert rho0 is not None, (
            'The "rho0" configuration option must be set in the '
            '"vertical_grid" section.'
        )

        x = resolution * np.array([-1.5, -0.5, 0.0, 0.5, 1.5], dtype=float)

        geom_ssh, geom_z_bot = self._get_geom_ssh_z_bot(x)

        vert_levels = config.getint('vertical_grid', 'vert_levels')
        if vert_levels is None:
            raise ValueError(
                'The "vert_levels" configuration option must be set in the '
                '"vertical_grid" section.'
            )

        vert_levs_inters = 2 * vert_levels + 1
        z_tilde = np.nan * np.ones((len(x), vert_levs_inters), dtype=float)
        z = np.nan * np.ones((len(x), vert_levs_inters), dtype=float)
        spec_vol = np.nan * np.ones((len(x), vert_levs_inters), dtype=float)
        ct = np.nan * np.ones((len(x), vert_levs_inters), dtype=float)
        sa = np.nan * np.ones((len(x), vert_levs_inters), dtype=float)

        z_tilde_node, temperature_node, salinity_node = (
            self._get_z_tilde_t_s_nodes(x)
        )

        for icol in range(len(x)):
            logger.info(f'Computing column {icol}, x = {x[icol]:.3f} km')
            (
                z_tilde[icol, :],
                z[icol, :],
                spec_vol[icol, :],
                ct[icol, :],
                sa[icol, :],
            ) = self._compute_column(
                z_tilde_node=z_tilde_node[icol, :],
                temperature_node=temperature_node[icol, :],
                salinity_node=salinity_node[icol, :],
                geom_ssh=geom_ssh.isel(nCells=icol).item(),
                geom_z_bot=geom_z_bot.isel(nCells=icol).item(),
            )

        # compute montgomery potential M = alpha * p + g * z
        g = constants['SHR_CONST_G']
        montgomery = g * (rho0 * spec_vol * z_tilde + z)

        # the HPGF is grad(M) - p * grad(alpha)
        # Here we just compute the gradient at x=0 using a 4th-order
        # finite-difference stencil
        p0 = rho0 * g * 0.5 * z_tilde[2, :]
        # indices for -1.5dx, -0.5dx, 0.5dx, 1.5dx
        grad_indices = [0, 1, 3, 4]
        dM_dx = _compute_4th_order_gradient(
            montgomery[grad_indices, :], resolution
        )
        dalpha_dx = _compute_4th_order_gradient(
            spec_vol[grad_indices, :], resolution
        )
        hpga = dM_dx - p0 * dalpha_dx

        ds = xr.Dataset()
        ds['temperature'] = xr.DataArray(
            data=ct[np.newaxis, 1:2, 1::2],
            dims=['Time', 'nCells', 'nVertLevels'],
            attrs={
                'long_name': 'conservative temperature',
                'units': 'degC',
            },
        )
        ds['salinity'] = xr.DataArray(
            data=sa[np.newaxis, 1:2, 1::2],
            dims=['Time', 'nCells', 'nVertLevels'],
            attrs={
                'long_name': 'salinity',
                'units': 'g kg-1',
            },
        )

        ds['SpecVol'] = xr.DataArray(
            data=spec_vol[np.newaxis, 1:2, 1::2],
            dims=['Time', 'nCells', 'nVertLevels'],
            attrs={
                'long_name': 'specific volume',
                'units': 'm3 kg-1',
            },
        )
        ds['Density'] = 1.0 / ds['SpecVol']
        ds.Density.attrs['long_name'] = 'density'
        ds.Density.attrs['units'] = 'kg m-3'

        ds['ZTildeMid'] = xr.DataArray(
            data=z_tilde[np.newaxis, 1:2, 1::2],
            dims=['Time', 'nCells', 'nVertLevels'],
        )
        ds.ZTildeMid.attrs['long_name'] = 'pseudo-height at layer midpoints'
        ds.ZTildeMid.attrs['units'] = 'm'

        ds['ZTildeInter'] = xr.DataArray(
            data=z_tilde[np.newaxis, 1:2, 0::2],
            dims=['Time', 'nCells', 'nVertLevelsP1'],
        )
        ds.ZTildeInter.attrs['long_name'] = 'pseudo-height at layer interfaces'
        ds.ZTildeInter.attrs['units'] = 'm'

        ds['GeomZMid'] = xr.DataArray(
            data=z[np.newaxis, 1:2, 1::2],
            dims=['Time', 'nCells', 'nVertLevels'],
            attrs={
                'long_name': 'geometric height at layer midpoints',
                'units': 'm',
            },
        )

        ds['GeomZInter'] = xr.DataArray(
            data=z[np.newaxis, 1:2, 0::2],
            dims=['Time', 'nCells', 'nVertLevelsP1'],
            attrs={
                'long_name': 'geometric height at layer interfaces',
                'units': 'm',
            },
        )

        ds['MontgomeryMid'] = xr.DataArray(
            data=montgomery[np.newaxis, 1:2, 1::2],
            dims=['Time', 'nCells', 'nVertLevels'],
            attrs={
                'long_name': 'Montgomery potential at layer midpoints',
                'units': 'm2 s-2',
            },
        )

        ds['MontgomeryInter'] = xr.DataArray(
            data=montgomery[np.newaxis, 1:2, 0::2],
            dims=['Time', 'nCells', 'nVertLevelsP1'],
            attrs={
                'long_name': 'Montgomery potential at layer interfaces',
                'units': 'm2 s-2',
            },
        )

        ds['HPGAMid'] = xr.DataArray(
            data=hpga[np.newaxis, 1::2],
            dims=['Time', 'nVertLevels'],
            attrs={
                'long_name': 'along-layer pressure gradient acceleration at '
                'midpoints',
                'units': 'm s-2',
            },
        )

        ds['HPGAInter'] = xr.DataArray(
            data=hpga[np.newaxis, 0::2],
            dims=['Time', 'nVertLevelsP1'],
            attrs={
                'long_name': 'along-layer pressure gradient acceleration at '
                'interfaces',
                'units': 'm s-2',
            },
        )

        self.write_model_dataset(ds, 'reference_solution.nc')

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
            xr.DataArray(data=geom_ssh, dims=['nCells']),
            xr.DataArray(data=geom_z_bot, dims=['nCells']),
        )

    def _init_z_tilde_interface(
        self, pseudo_bottom_depth: float
    ) -> tuple[np.ndarray, int]:
        """
        Compute z-tilde vertical interfaces.
        """
        section = self.config['vertical_grid']
        vert_levels = section.getint('vert_levels')
        bottom_depth = section.getfloat('bottom_depth')
        z_tilde_interface = np.linspace(
            0.0, -bottom_depth, vert_levels + 1, dtype=float
        )
        z_tilde_interface = np.maximum(z_tilde_interface, -pseudo_bottom_depth)
        dz = z_tilde_interface[0:-1] - z_tilde_interface[1:]
        mask = dz == 0.0
        z_tilde_interface[1:][mask] = np.nan

        # max_layer is the index of the deepest non-nan layer interface
        max_layer = np.where(~mask)[0][-1] + 1
        return z_tilde_interface, max_layer

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

        self.logger.debug('z_tilde nodes:')
        self.logger.debug(z_tilde_node)
        self.logger.debug('temperature nodes:')
        self.logger.debug(t_node)
        self.logger.debug('salinity nodes:')
        self.logger.debug(s_node)

        return z_tilde_node, t_node, s_node

    def _compute_column(
        self,
        z_tilde_node: np.ndarray,
        temperature_node: np.ndarray,
        salinity_node: np.ndarray,
        geom_ssh: float,
        geom_z_bot: float,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        config = self.config
        logger = self.logger
        section = config['two_column']
        method = section.get('reference_quadrature_method')
        assert method is not None, (
            'The "reference_quadrature_method" configuration option must be '
            'set in the "two_column" section.'
        )
        rho0 = config.getfloat('vertical_grid', 'rho0')
        assert rho0 is not None, (
            'The "rho0" configuration option must be set in the '
            '"vertical_grid" section.'
        )
        water_col_adjust_iter_count = section.getint(
            'water_col_adjust_iter_count'
        )
        assert water_col_adjust_iter_count is not None, (
            'The "water_col_adjust_iter_count" configuration option must be '
            'set in the "two_column" section.'
        )

        goal_geom_water_column_thickness = geom_ssh - geom_z_bot

        # first guess at the pseudo bottom depth is the geometric
        # water column thickness
        pseudo_bottom_depth = goal_geom_water_column_thickness

        logger.debug(
            f'goal_geom_water_column_thickness = '
            f'{goal_geom_water_column_thickness:.12f}'
        )

        for iter in range(water_col_adjust_iter_count):
            z_tilde_inter, max_layer = self._init_z_tilde_interface(
                pseudo_bottom_depth=pseudo_bottom_depth
            )
            vert_levels = len(z_tilde_inter) - 1

            z_tilde_mid = 0.5 * (z_tilde_inter[0:-1] + z_tilde_inter[1:])

            # z_tilde has both interfaces and midpoints
            z_tilde = np.zeros(2 * vert_levels + 1, dtype=float)
            z_tilde[0::2] = z_tilde_inter
            z_tilde[1::2] = z_tilde_mid

            valid = slice(0, 2 * max_layer + 1)

            z_tilde_valid = z_tilde[valid]
            logger.debug(f'z_tilde_valid = {z_tilde_valid}')
            logger.debug(f'z_tilde invalid = {z_tilde[2 * max_layer + 1 :]}')

            z = np.nan * np.ones_like(z_tilde)
            spec_vol = np.nan * np.ones_like(z_tilde)
            ct = np.nan * np.ones_like(z_tilde)
            sa = np.nan * np.ones_like(z_tilde)

            (
                z[valid],
                spec_vol[valid],
                ct[valid],
                sa[valid],
            ) = integrate_geometric_height(
                z_tilde_interfaces=z_tilde_valid,
                z_tilde_nodes=z_tilde_node,
                sa_nodes=salinity_node,
                ct_nodes=temperature_node,
                bottom_depth=-geom_z_bot,
                rho0=rho0,
                method=method,
            )

            geom_water_column_thickness = z[0] - z[2 * max_layer]

            scaling_factor = (
                goal_geom_water_column_thickness / geom_water_column_thickness
            )
            logger.info(
                f'   Iteration {iter}: '
                f'scaling factor = {scaling_factor:.12f}, '
                f'scaling factor - 1 = {scaling_factor - 1.0:.12g}, '
                f'pseudo bottom depth = {pseudo_bottom_depth:.12f}, '
                f'max layer = {max_layer}'
            )
            pseudo_bottom_depth *= scaling_factor
        logger.info('')

        return z_tilde, z, spec_vol, ct, sa


def _compute_4th_order_gradient(f: np.ndarray, dx: float) -> np.ndarray:
    """
    Compute a 4th-order finite-difference gradient of f with respect to x
    at x=0, assuming values at x = dx * [-1.5, -0.5, 0.5, 1.5].

    The stencil is:
        f'(0) ≈ [-f(1.5dx) + 9 f(0.5dx) - 9 f(-0.5dx) + f(-1.5dx)] / (8 dx)

    Here we assume f[0,:], f[1,:], f[2,:], f[3,:] correspond to
    x = -1.5dx, -0.5dx, 0.5dx, 1.5dx respectively.
    """
    assert f.shape[0] == 4, (
        'Input array must have exactly 4 entries in its first dimension '
        'for the 4th-order gradient.'
    )

    # gradient at x = 0 using the non-uniform 4-point stencil
    df_dx = (-f[3, :] + 9.0 * f[2, :] - 9.0 * f[1, :] + f[0, :]) / (8.0 * dx)

    return df_dx
