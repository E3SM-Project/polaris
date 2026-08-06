import matplotlib.pyplot as plt
import numpy as np

from polaris.ocean.model import OceanIOStep
from polaris.ocean.model.time import get_days_since_start
from polaris.viz import use_mplstyle


class StatsAnalysis(OceanIOStep):
    def __init__(
        self,
        component,
        indir,
        forward_step,
        output_filename='global_stats.nc',
        name='global_stats',
    ):
        # TODO this should be replaced with model-specific state variables
        # read from yaml
        self.forward_step = forward_step
        self.output_filename = output_filename
        super().__init__(
            component=component,
            name=name,
            indir=indir,
        )
        if component.state_vars is None:
            component._read_variables_yaml()
        self.variables = component.state_vars

    def setup(self):
        model = self.config.get('ocean', 'model')
        if model == 'omega':
            filename = self.output_filename.split('.')[0]
            target = f'{self.forward_step.path}/{filename}_1DayTimeStats'
        else:
            target = f'{self.forward_step.path}/{self.output_filename}'
        self.add_input_file(
            filename='output.nc',
            work_dir_target=target,
        )
        for variable_name in self.variables:
            self.add_output_file(f'{variable_name}_stats.png')

    def run(self):
        use_mplstyle()
        model = self.config.get('ocean', 'model')
        ds = self.open_model_dataset('output.nc', self.config)
        if 'Scalar' in ds.dims:
            ds = ds.isel(Scalar=0)
        time = get_days_since_start(ds)
        for variable_name in self.variables:
            fig, axes = plt.subplots(
                nrows=2, ncols=1, sharex=True, sharey=False, figsize=(5, 8)
            )
            suffix = 'Min'
            var = ds[f'{variable_name}{suffix}']
            axes[0].plot(time, var, ':k', label=suffix)
            axes[1].plot(time, var - var[0], ':k', label=suffix)
            suffix = 'Max'
            var = ds[f'{variable_name}{suffix}']
            axes[0].plot(time, var, '--k', label=suffix)
            axes[1].plot(time, var - var[0], '--k', label=suffix)
            suffix = 'Avg'
            var_mean = ds[f'{variable_name}{suffix}']
            axes[0].plot(time, var_mean, '-k', label=suffix)
            axes[1].plot(time, var_mean - var_mean[0], '-k', label=suffix)
            suffix = 'Rms'
            if model == 'omega':
                var_std = ds[f'{variable_name}{suffix}'].values
            else:
                var_rms = ds[f'{variable_name}{suffix}']
                var_std = np.sqrt(var_rms.values**2.0 - var_mean.values**2.0)
            axes[0].fill_between(
                time,
                var_mean.values + var_std,
                var_mean.values - var_std,
                color='k',
                alpha=0.5,
                label='SD',
            )
            axes[0].legend()
            axes[1].legend()
            axes[0].set_xlabel('Days')
            axes[1].set_xlabel('Days')
            axes[0].set_ylabel(variable_name)
            axes[1].set_ylabel(f'{variable_name} - {variable_name} at t=0')
            axes[0].set_xlim([min(time), max(time)])
            fig.savefig(f'{variable_name}_stats.png', bbox_inches='tight')
            plt.close(fig)
