import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import MaxNLocator

from polaris.constants import get_constant
from polaris.ocean.model import OceanIOStep, get_time_since_start
from polaris.ocean.vertical.diagnostics import vertical_coord_from_location
from polaris.viz import mplstyle_context


class Analysis(OceanIOStep):
    """
    A step for comparing the velocity profile to an analytic solution
    """

    def __init__(self, component, indir, forward):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        indir : str
            The subdirectory that the task belongs to, that this step will
            go into a subdirectory of

        forward : polaris.Step
            The forward step for this test case

        """
        super().__init__(component=component, name='analysis', indir=indir)
        self.forward = forward

    def setup(self):
        self.add_input_file(
            filename='mesh.nc',
            target=f'{self.base_work_dir}/{self.forward.path}/mesh.nc',
        )
        self.add_input_file(
            filename='output.nc',
            target=f'{self.base_work_dir}/{self.forward.path}/output.nc',
        )

    def run(self):
        """
        Run this step of the test case
        """
        ds = self.open_model_dataset(
            'output.nc',
            self.config,
            decode_times=True,
            mesh_filename='mesh.nc',
            reconstruct_variables=['normalVelocity'],
        )
        times = get_time_since_start(ds, units='seconds')
        config = self.config
        f = config.getfloat('coriolis', 'constant_f')
        end = config.getfloat('single_column', 'run_duration') * 86400.0
        duration = (
            config.getint('single_column_ekman', 'averaging_periods')
            * 2.0
            * np.pi
            / abs(f)
        )
        start = end - duration
        if (
            times.size < 2
            or not np.isfinite(start)
            or duration <= 0.0
            or start < 0.0
            or not np.all(np.isfinite(times))
            or np.any(np.diff(times) <= 0.0)
            or times[0] > start
            or times[-1] < end
        ):
            raise ValueError(
                'Run duration and output must cover the final steady '
                'averaging window with finite, strictly increasing times'
            )
        numeric = [
            name
            for name in ds.data_vars
            if np.issubdtype(ds[name].dtype, np.number)
        ]
        ds = ds[numeric].assign_coords(Time=times)
        samples = np.concatenate(
            ([start], times[(times > start) & (times < end)], [end])
        )
        sampled = ds.interp(Time=samples)
        averaged = sampled.isel(Time=-1, drop=True).copy()
        for name in sampled.data_vars:
            if 'Time' in sampled[name].dims:
                averaged[name] = sampled[name].integrate('Time') / duration
        self.logger.info(
            f'Steady window: days {start / 86400.0:.6f} to {end / 86400.0:.6f}'
        )
        self._analyze_profile(averaged, 'steady')

    def _analyze_profile(self, ds, label):
        logger = self.logger
        with mplstyle_context():
            config = self.config
            f = config.getfloat('coriolis', 'constant_f')
            bottom_depth = config.getfloat('vertical_grid', 'bottom_depth')
            tau_x = config.getfloat(
                'single_column_forcing', 'wind_stress_zonal'
            )
            nu = config.getfloat('single_column_ekman', 'vertical_viscosity')

            z_mid = (
                vertical_coord_from_location(ds, 'cell-center')
                .mean(dim='nCells')
                .values
            )
            if 'density' in ds.keys():
                rho_0 = (
                    ds['density'].mean(dim='nCells').isel(nVertLevels=0).values
                )
            elif 'SpecVol' in ds.keys():
                rho_0 = np.divide(
                    1,
                    ds['SpecVol']
                    .mean(dim='nCells')
                    .isel(nVertLevels=0)
                    .values,
                )
            else:
                rho_0 = get_constant('seawater_density_reference')
            u = ds['velocityZonal'].mean(dim='nCells')
            v = ds['velocityMeridional'].mean(dim='nCells')
            u_exact, v_exact = _exact_solution(
                z_mid, nu, f, tau_x=tau_x / rho_0
            )
            thickness = ds['layerThickness'].mean(dim='nCells').values
            z_top = z_mid + 0.5 * thickness
            z_bottom = z_mid - 0.5 * thickness
            z_max = bottom_depth / 3.0
            weights = np.maximum(
                0.0, np.minimum(z_top, 0.0) - np.maximum(z_bottom, -z_max)
            )
            exact_speed_squared = u_exact**2 + v_exact**2
            diff_speed_squared = (u.values - u_exact) ** 2 + (
                v.values - v_exact
            ) ** 2
            analytic_error = np.sqrt(
                np.sum(weights * diff_speed_squared)
                / np.sum(weights * exact_speed_squared)
            )
            if not np.isfinite(analytic_error):
                raise ValueError(
                    f'{label}: nonfinite relative L2 error of Ekman profile'
                )

            fig, (profile_ax, diff_ax) = plt.subplots(
                1, 2, figsize=(8, 5), sharey=True
            )
            profile_ax.plot(u_exact, z_mid, '-k', label='u analytic')
            profile_ax.plot(u, z_mid, '.k', label='u model')
            profile_ax.plot(v_exact, z_mid, '-b', label='v analytic')
            profile_ax.plot(v, z_mid, '.b', label='v model')
            profile_ax.set_xlabel('Velocity (m/s)')
            profile_ax.set_ylabel('z (m)')
            profile_ax.set_title('Velocity profiles')
            profile_ax.legend()

            diff_ax.axvline(0.0, color='0.5', linewidth=0.8)
            diff_ax.plot(u.values - u_exact, z_mid, '-k', label='delta u')
            diff_ax.plot(v.values - v_exact, z_mid, '-b', label='delta v')
            diff_ax.set_xlabel('Model - analytic (m/s)')
            diff_ax.set_title('Velocity difference')
            diff_ax.xaxis.set_major_locator(MaxNLocator(nbins=5))
            diff_ax.ticklabel_format(axis='x', style='sci', scilimits=(0, 0))
            diff_ax.legend()
            fig.suptitle(f'Ekman velocity: {label}')
            fig.tight_layout(pad=0.5)
            fig.savefig(f'velocity_comparison_{label}.png')
            plt.close()

            # Write out some information about the error
            logger.info(
                f'{label}: relative L2 error of Ekman profile over the top '
                f'third: {analytic_error:.3%}'
            )


def _exact_solution(depth, nu, f, u_g=0.0, v_g=0.0, tau_x=0.0, tau_y=0.0):
    """Evaluate the original steady, semi-infinite Ekman spiral."""
    ekman_depth = (2 * nu / f) ** 0.5
    u_0 = 2**0.5 * tau_x / (ekman_depth * f)
    v_0 = 2**0.5 * tau_y / (ekman_depth * f)
    z = depth / ekman_depth
    u = u_g + np.exp(z) * (
        u_0 * np.cos(z - np.pi / 4.0) - v_0 * np.sin(z - np.pi / 4.0)
    )
    v = v_g + np.exp(z) * (
        u_0 * np.sin(z - np.pi / 4.0) + v_0 * np.cos(z - np.pi / 4.0)
    )
    return u, v
