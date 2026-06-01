import matplotlib.pyplot as plt
import numpy as np

from polaris.ocean.model import OceanIOStep
from polaris.viz import use_mplstyle


class StatsAnalysis(OceanIOStep):
    def __init__(self, component, name, indir, output_filename, forward_step):
        # TODO this should be replaced with model-specific state variables
        # read from yaml
        self.variables = [
            'temperature',
            'salinity',
            'layerThickness',
            'normalVelocity',
        ]
        self.forward_step = forward_step
        self.output_filename = output_filename
        super().__init__(
            component=component,
            name=name,
            indir=indir,
        )

    def setup(self):
        self.add_input_file(
            filename='output.nc',
            target=f'../{self.forward_step.path}/{self.output_filename}',
        )
        for variable_name in self.variables:
            self.add_output_file(f'{variable_name}_stats.png')

    def run(self):
        use_mplstyle()
        ds = self.open_model_dataset('output.nc', self.config)
        time_variable = 'daysSinceStartOfSim'
        time = ds[time_variable]
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
            var_rms = ds[f'{variable_name}{suffix}']
            var_std = np.sqrt(var_rms.values**2.0 - var_mean.values**2.0)
            axes[0].fill_between(
                time,
                var_mean + var_std,
                var_mean - var_std,
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
