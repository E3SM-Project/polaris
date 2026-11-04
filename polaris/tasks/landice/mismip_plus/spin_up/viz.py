import xarray as xr

from polaris import Step
from polaris.tasks.landice.mismip_plus.output import read_output
from polaris.tasks.landice.mismip_plus.plot import (
    plot_global_stats,
    plot_thickness_and_speed,
    plot_time_series,
)


class SpinUpViz(Step):
    """
    A step for plotting the MISMIP+ steady state and how the spin-up reached
    it
    """

    def __init__(self, component, run_step, spin_up, indir):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        run_step : polaris.tasks.landice.mismip_plus.spin_up.SpinUpRun
            The step that runs MALI

        spin_up : polaris.tasks.landice.mismip_plus.spin_up.SpinUp
            The shared step with the steady state

        indir : str
            the directory the step is in, to which ``name`` will be appended
        """
        super().__init__(component=component, name='viz', indir=indir)
        for filename in ['steady_state.nc', 'spin_up_diagnostics.nc']:
            self.add_input_file(
                filename=filename,
                work_dir_target=f'{spin_up.path}/{filename}',
            )
        self.add_input_file(
            filename='global_stats.nc',
            work_dir_target=f'{run_step.path}/globalStats.nc',
        )
        for filename in [
            'steady_state_thickness.png',
            'steady_state_surface_speed.png',
            'spin_up_diagnostics.png',
            'spin_up_global_stats_volume.png',
            'spin_up_global_stats_flux.png',
        ]:
            self.add_output_file(filename=filename)

    def run(self):
        """
        Run this step
        """
        ds = xr.open_dataset('steady_state.nc').isel(Time=0)
        plot_thickness_and_speed(
            ds, self.config, prefix='steady_state_', title='at steady state'
        )
        ds_diag = xr.open_dataset('spin_up_diagnostics.nc')
        plot_time_series(
            [('spin-up', ds_diag)],
            filename='spin_up_diagnostics.png',
            title='MISMIP+ spin-up',
        )
        plot_global_stats(
            [('spin-up', read_output('global_stats.nc'))],
            prefix='spin_up_',
            title='MISMIP+ spin-up',
        )
