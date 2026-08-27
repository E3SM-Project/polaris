import numpy as np

from polaris.ocean.analysis_plots import plot_global_stats
from polaris.ocean.model import OceanIOStep
from polaris.ocean.model.time import get_days_since_start


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
        model = self.config.get('ocean', 'model')
        ds = self.open_model_dataset('output.nc', self.config)
        if 'Scalar' in ds.dims:
            ds = ds.isel(Scalar=0)
        time = get_days_since_start(ds)
        for variable_name in self.variables:
            var_mean = ds[f'{variable_name}Avg'].values
            var_rms = ds[f'{variable_name}Rms'].values
            if model == 'omega':
                # Omega's Rms is mapped from SpatialStdDev, so it already is
                # a standard deviation
                var_std = var_rms
            else:
                var_std = np.sqrt(var_rms**2.0 - var_mean**2.0)
            stats = {
                'min': ds[f'{variable_name}Min'].values,
                'max': ds[f'{variable_name}Max'].values,
                'mean': var_mean,
                'std': var_std,
            }
            plot_global_stats(
                time=time,
                stats=stats,
                field_name=variable_name,
                out_filename=f'{variable_name}_stats.png',
            )
