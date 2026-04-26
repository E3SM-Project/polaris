import matplotlib.pyplot as plt
import numpy as np

from polaris.ocean.model import OceanIOStep, get_days_since_start
from polaris.viz import use_mplstyle


class Analysis(OceanIOStep):
    """
    The analysis step plots a time series showing inertial oscillations
    computes the oscillation frequency, and compares it to the theoretical
    frequency
    """

    def __init__(self, component, indir, config):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        indir : str
            The subdirectory that the task belongs to, that this step will
            go into a subdirectory of

        config : polaris.config.PolarisConfigParser
            Config options for test case
        """
        super().__init__(component=component, name='analysis', indir=indir)
        self.config = config
        self.add_input_file(
            filename='output.nc', target='../forward/output.nc'
        )

    # def setup(self):
    #    model = self.config.get('ocean', 'model')
    #    # TODO: remove as soon as Omega no longer needs this file
    #    if model == 'omega':
    #        self.add_input_file(
    #            target='coeffs.nc',
    #            filename='coeffs.nc',
    #            database='single_column',
    #        )

    def run(self):
        """
        Run this step of the test case
        """
        logger = self.logger
        use_mplstyle()

        config = self.config
        f = config.getfloat('single_column', 'coriolis_parameter')
        tol = config.getfloat(
            'single_column_inertial', 'period_tolerance_fraction'
        )

        ds = self.open_model_dataset(
            'output.nc',
            decode_times=True,
            mesh_filename='../init/initial_state.nc',
            reconstruct_variables=['normalVelocity'],
            coeffs_filename='../forward/coeffs_reconstruct.nc',
        )
        t = get_days_since_start(ds)
        s_per_day = 24.0 * 3600.0
        dt = (t[1] - t[0]) * s_per_day
        t_index = np.argmin(np.abs(t - 1.0))  # ds.sizes['Time'] - 1
        u = ds['velocityZonal'].mean(dim='nCells')
        v = ds['velocityMeridional'].mean(dim='nCells')
        u_max = np.max(u.values, axis=1)
        v_max = np.max(v.values, axis=1)

        # Compute the FFT of the u-component and extract the frequency with
        # the most power
        freq = np.fft.fftfreq(len(u_max), dt)
        power = abs(np.fft.fft(u_max))
        dominant_frequency = abs(freq[np.argmax(power[1:]) + 1])
        dominant_period = (1 / dominant_frequency) / 3600.0  # in hours
        expected_period = (2 * np.pi / f) / 3600.0  # in hours

        # Plot a time series of the maximum u and v components
        plt.figure(figsize=(3, 5))
        ax = plt.subplot(111)
        ax.plot(t[:t_index], u_max[:t_index], '-b')
        ax.plot(t[:t_index], v_max[:t_index], '--b')
        ymin, ymax = ax.get_ylim()
        ax.plot(
            [expected_period / 24.0, expected_period / 24.0],
            [ymin, ymax],
            '--g',
        )
        ax.plot(
            [dominant_period / 24.0, dominant_period / 24.0],
            [ymin, ymax],
            '--k',
        )
        ax.set_xlabel('Time (days)')
        ax.set_ylabel('Maximum velocity (m/s)')
        ax.set_ylim([ymin, ymax])
        plt.tight_layout(pad=0.5)
        plt.savefig('velocity_tseries.png')
        plt.close()

        # Write out some information about the inertial oscillations
        logger.info(f'Dominant period: {dominant_period:1.3f} (h)')
        logger.info(
            'Expected period for inertial oscillations: '
            f'{expected_period:1.3f} (h)'
        )

        period_frac_diff = (
            dominant_period - expected_period
        ) / expected_period

        # Test case fails if the oscillations have a frequency that is too
        # different from the theoretical frequency
        if abs(period_frac_diff) > tol:
            logger.error(
                'error: Discrepancy in inertial oscillation frequency '
                f'{period_frac_diff * 1.0e2} %\n'
                f'  max fractional tolerance {tol}'
            )
            raise ValueError(
                'Inertial oscillation falls outside expected frequency'
            )
