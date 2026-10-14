import numpy as np
import xarray as xr

from polaris.ocean.analysis_plots import plot_global_stats
from polaris.ocean.global_stats_names import (
    discover_fields,
    select_global_stats,
)
from polaris.ocean.model import OceanIOStep
from polaris.ocean.model.time import get_time_since_start
from polaris.tasks.ocean.realistic_global.forward.stage import ForwardStage


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
        self.forward_step = forward_step
        self.output_filename = output_filename
        super().__init__(
            component=component,
            name=name,
            indir=indir,
        )

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

    def run(self):
        model = self.config.get('ocean', 'model')
        ds = xr.open_dataset(self.work_path('output.nc'))
        if 'Scalar' in ds.dims:
            ds = ds.isel(Scalar=0)

        fields = self._fields(ds, model)
        found = select_global_stats(
            ds=ds,
            fields=fields,
            stats=None,
            model=model,
            field_map=self._field_map(fields, model),
            log=self.logger.info,
            source='output.nc',
            hint=(
                'Check that the global statistics analysis member was '
                'enabled for the fields the plots are asked for.'
            ),
        )

        ds_time = ds.rename({'time': 'Time'}) if 'time' in ds.dims else ds
        time = get_time_since_start(ds_time, units='days')
        for field, field_stats in found.items():
            values = {
                stat: ds[var_name].values.astype(float)
                for stat, var_name in field_stats.items()
            }
            _add_standard_deviation(values)
            filename = f'{field}_stats.png'
            plot_global_stats(
                time=time,
                stats=values,
                field_name=field,
                out_filename=self.work_path(filename),
            )
            self.add_produced_file(filename)

    def _fields(self, ds, model):
        """Get the fields to plot, in Polaris-standard names"""
        fields = self.config.getlist(
            'realistic_global_forward_stats', 'fields'
        )
        if fields:
            return fields
        # the honest default: whatever the run wrote statistics for
        return self.component.map_var_list_from_native_model(
            discover_fields(ds, model=model)
        )

    def _field_map(self, fields, model):
        """Get the name the model gave each field"""
        native = self.component.map_var_list_to_native_model(fields)
        return dict(zip(fields, native, strict=True))


def _add_standard_deviation(values):
    """
    Get a standard deviation for the plot's envelope, deriving one from the
    root-mean-square if that is what the model computed

    MPAS-Ocean writes a root-mean-square where Omega writes a standard
    deviation, so this is where the two are reconciled -- a conversion rather
    than a difference of spelling, which is why it is not in the table of
    names.
    """
    if 'std' in values or 'rms' not in values or 'mean' not in values:
        return
    mean = values['mean']
    rms = values['rms']
    values['std'] = np.sqrt(rms**2.0 - mean**2.0)
