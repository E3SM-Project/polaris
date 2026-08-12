import matplotlib.pyplot as plt
import numpy as np

from polaris.ocean.model import OceanIOStep
from polaris.ocean.model.time import get_days_since_start
from polaris.tasks.ocean.realistic_global.forward.stage import ForwardStage
from polaris.viz import use_mplstyle


class StatsAnalysis(OceanIOStep):
    """
    A step for plotting time series of a forward run's global statistics.

    Both models write the global minimum, maximum, mean and spread of each
    state variable, but not in the same form: MPAS-Ocean writes a root mean
    square where Omega writes a standard deviation, so the MPAS-Ocean values
    are converted before plotting.

    Attributes
    ----------
    forward_step : polaris.Step
        The forward step whose statistics are plotted.

    output_filename : str
        The MPAS-Ocean statistics file, and the prefix of the Omega one.
    """

    def __init__(
        self,
        component,
        indir,
        forward_step,
        output_filename='global_stats.nc',
        name='global_stats',
    ):
        """
        Create the step.

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the step belongs to.

        indir : str
            The directory the step is in, to which ``name`` is appended.

        forward_step : polaris.Step
            The forward step whose statistics are plotted.

        output_filename : str, optional
            The name MPAS-Ocean writes its statistics to.  Omega uses the same
            name without its extension as a filename prefix.

        name : str, optional
            The name of the step.
        """
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
        """
        Link the forward step's statistics file.

        What the file is called depends on the model and, for Omega, on the
        statistics period, so the name comes from
        :py:meth:`~polaris.tasks.ocean.realistic_global.forward.stage.ForwardStage.stats_filename`
        on the same stage the forward step renders its config from.  That is
        also why the entry is added here rather than in ``__init__()``, where
        the model is not yet known.
        """
        model = self.config.get('ocean', 'model')
        stage = getattr(self.forward_step, 'stage', None)
        if stage is None:
            stage = ForwardStage.from_config(self.config)
        filename = stage.stats_filename(model, self.output_filename)
        target = f'{self.forward_step.path}/{filename}'
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
