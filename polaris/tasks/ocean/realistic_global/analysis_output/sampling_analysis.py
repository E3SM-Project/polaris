from typing import Dict, List

import numpy as np
import pandas as pd
import xarray as xr
from matplotlib.figure import Figure
from matplotlib.ticker import NullFormatter

from polaris.ocean.model import OceanIOStep
from polaris.tasks.ocean.realistic_global.forward import ForwardStage
from polaris.viz import mplstyle_context

#: Colors and markers for the fields in the convergence plot, in a fixed
#: order, so that each field keeps its color and marker whatever the others
_FIELD_STYLES = [
    ('#2a78d6', 'o'),
    ('#eb6834', 's'),
    ('#1baf7a', '^'),
    ('#eda100', 'D'),
]


class SamplingAnalysis(OceanIOStep):
    """
    Check how Omega's time means converge with their sampling interval

    For each field, the error of each sampled run's means is the relative L2
    norm of their difference from the reference run's means, over both
    averaging periods.  Each mean sums samples taken at the end of each
    sampling interval, so a run that samples every ``n`` time steps differs
    from the every-step reference at first order in ``(n - 1) dt``.  The
    order of convergence is fit against that.  The time means of the run
    with the coarsest sampling are then checked against the means of the
    history snapshots that run wrote at its samples, which pins down the
    sample times and their number.

    Attributes
    ----------
    run_names : list of str
        The forward steps, the reference run first

    sampling_steps : list of int
        The number of time steps between samples in each sampled run

    mean_filenames : list of str
        The time-mean file of each averaging period, in each forward step

    reduction_period : str
        The averaging period as Omega spells it

    period_seconds : float
        The averaging period in seconds

    min_res : float
        The minimum resolution of the mesh in km
    """

    def __init__(
        self,
        component,
        indir: str,
        run_names: List[str],
        sampling_steps: List[int],
        mean_filenames: List[str],
        reduction_period: str,
        period_seconds: float,
        min_res: float,
    ):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        indir : str
            the directory the step is in, to which ``name`` will be appended

        run_names : list of str
            The forward steps, the reference run first and the run with the
            coarsest sampling, which wrote the snapshots, last

        sampling_steps : list of int
            The number of time steps between samples in each sampled run

        mean_filenames : list of str
            The time-mean file of each averaging period, in each forward step

        reduction_period : str
            The averaging period as Omega spells it

        period_seconds : float
            The averaging period in seconds

        min_res : float
            The minimum resolution of the mesh in km
        """
        super().__init__(component=component, name='analysis', indir=indir)
        self.run_names = run_names
        self.sampling_steps = sampling_steps
        self.mean_filenames = mean_filenames
        self.reduction_period = reduction_period
        self.period_seconds = period_seconds
        self.min_res = min_res

        for run_name in run_names:
            for filename in mean_filenames:
                self.add_input_file(
                    filename=f'{run_name}_{filename}',
                    target=f'../{run_name}/{filename}',
                )
        self.add_input_file(
            filename='snapshots.nc', target=f'../{run_names[-1]}/output.nc'
        )
        self.add_output_file(filename='convergence.csv')
        self.add_output_file(filename='convergence.png')

    def run(self):
        """
        Fit the order of convergence of each field's time means, and check
        the means of the coarsest sampling against its snapshots
        """
        super().run()
        config = self.config
        logger = self.logger
        section = 'analysis_output_sampling'
        fields = config.getlist(section, 'fields')
        convergence_fields = config.getlist(section, 'convergence_fields')
        unknown = sorted(set(convergence_fields) - set(fields))
        if unknown:
            raise ValueError(
                f'convergence_fields {unknown} are not among the averaged '
                f'fields {fields}.'
            )
        order_min = config.getfloat(section, 'order_min')
        order_max = config.getfloat(section, 'order_max')
        exact_rtol = config.getfloat(section, 'exact_rtol')

        dt = ForwardStage.from_config(config).time_step_seconds(
            model=config.get('ocean', 'model'), min_res=self.min_res
        )
        offsets = np.array([(n - 1) * dt for n in self.sampling_steps])

        reference_run = self.run_names[0]
        sampled_runs = self.run_names[1:]
        errors: Dict[str, np.ndarray] = {}
        orders: Dict[str, float] = {}
        rows = []
        for field in fields:
            reference = self._read_means(reference_run, field)
            field_errors = []
            for run_name, steps in zip(
                sampled_runs, self.sampling_steps, strict=True
            ):
                error = relative_l2_error(
                    self._read_means(run_name, field), reference
                )
                field_errors.append(error)
                rows.append(
                    dict(
                        field=field,
                        sampling_steps=steps,
                        sampling_interval_s=steps * dt,
                        relative_l2_error=error,
                    )
                )
            errors[field] = np.array(field_errors)
            orders[field] = fit_order(offsets, errors[field])

        pd.DataFrame(rows).to_csv(self.work_path('convergence.csv'))
        self._plot(fields, convergence_fields, offsets, errors, orders)

        all_pass = True
        logger.info('Order of convergence with the sampling interval:')
        for field in fields:
            order = orders[field]
            if field not in convergence_fields:
                logger.info(f'  {field:<16} {order:6.3f} (not checked)')
                continue
            passed = order_min <= order <= order_max
            result = 'PASS' if passed else 'FAIL'
            logger.info(
                f'  {field:<16} {order:6.3f} (bounds {order_min} to '
                f'{order_max}) {result}'
            )
            all_pass = all_pass and passed

        all_pass = self._check_snapshot_means(fields, dt, exact_rtol) and (
            all_pass
        )

        if not all_pass:
            raise ValueError(
                'The time means did not converge as expected with their '
                'sampling interval; see the log for details.'
            )

    def _read_means(self, run_name: str, field: str) -> np.ndarray:
        """
        Read a field's time means from every averaging period of a run, with
        the inactive layers as NaN
        """
        variable = f'{field}_TimeMean{self.reduction_period}'
        means = []
        for filename in self.mean_filenames:
            with xr.open_dataset(
                f'{run_name}_{filename}', decode_times=False
            ) as ds:
                means.append(ds[variable].values)
        return np.concatenate(means, axis=0)

    def _check_snapshot_means(
        self, fields: List[str], dt: float, exact_rtol: float
    ) -> bool:
        """
        Check the time means of the run with the coarsest sampling against
        the means of the snapshots it wrote at its samples
        """
        logger = self.logger
        steps = self.sampling_steps[-1]
        expected_count = int(round(self.period_seconds / (steps * dt)))
        run_name = self.run_names[-1]

        all_pass = True
        logger.info(
            f'Time means of {run_name} compared with the means of its '
            f'{expected_count} snapshots per period:'
        )
        with xr.open_dataset('snapshots.nc', decode_times=False) as ds:
            times = ds.time.values
            for index, filename in enumerate(self.mean_filenames):
                period_end = (index + 1) * self.period_seconds
                in_period = select_period(
                    times, period_end - self.period_seconds, period_end
                )
                count = np.count_nonzero(in_period)
                if count != expected_count:
                    logger.error(
                        f'  {filename}: {count} snapshots in the period, '
                        f'expected {expected_count} FAIL'
                    )
                    all_pass = False
                    continue
                variable_suffix = f'_TimeMean{self.reduction_period}'
                with xr.open_dataset(
                    f'{run_name}_{filename}', decode_times=False
                ) as ds_means:
                    for field in fields:
                        means = ds_means[f'{field}{variable_suffix}'].values
                        snapshot_mean = np.mean(
                            ds[field].values[in_period], axis=0
                        )
                        # Omega's means mark the inactive layers
                        difference = relative_max_difference(
                            snapshot_mean, means[0]
                        )
                        passed = difference <= exact_rtol
                        result = 'PASS' if passed else 'FAIL'
                        logger.info(
                            f'  {filename} {field:<16} {difference:.3e} '
                            f'(tolerance {exact_rtol:.1e}) {result}'
                        )
                        all_pass = all_pass and passed
        return all_pass

    def _plot(
        self,
        fields: List[str],
        convergence_fields: List[str],
        offsets: np.ndarray,
        errors: Dict[str, np.ndarray],
        orders: Dict[str, float],
    ):
        """
        Plot each field's error against the sampling interval
        """
        minutes = offsets / 60.0
        with mplstyle_context():
            fig = Figure()
            ax = fig.add_subplot(111)
            for index, field in enumerate(fields):
                color, marker = _FIELD_STYLES[index % len(_FIELD_STYLES)]
                label = f'{field} (order {orders[field]:.2f})'
                if field not in convergence_fields:
                    label = f'{field} (order {orders[field]:.2f}, unchecked)'
                ax.loglog(
                    minutes,
                    errors[field],
                    color=color,
                    marker=marker,
                    linewidth=2,
                    markersize=8,
                    label=label,
                )
            # a first-order guide through the geometric mean of the errors
            all_errors = np.concatenate(list(errors.values()))
            anchor = np.exp(np.mean(np.log(all_errors)))
            guide = anchor * minutes / np.exp(np.mean(np.log(minutes)))
            ax.loglog(
                minutes,
                guide,
                '--',
                color='0.5',
                linewidth=1,
                label='first order',
            )
            ax.set_xticks(minutes)
            ax.set_xticklabels([f'{value:g}' for value in minutes])
            ax.xaxis.set_minor_formatter(NullFormatter())
            ax.set_xlabel('sampling interval minus time step (minutes)')
            ax.set_ylabel('relative L2 error of the time means')
            ax.set_title('Convergence of time means with sampling interval')
            ax.legend(loc='upper left', bbox_to_anchor=(1.02, 1.0))
            fig.savefig(
                self.work_path('convergence.png'),
                bbox_inches='tight',
                pad_inches=0.1,
            )


def relative_l2_error(values: np.ndarray, reference: np.ndarray) -> float:
    """
    The L2 norm of the difference between two arrays relative to that of the
    reference, over the points where both are finite

    Parameters
    ----------
    values : numpy.ndarray
        The values

    reference : numpy.ndarray
        The reference values

    Returns
    -------
    error : float
        The relative L2 error
    """
    valid = np.isfinite(values) & np.isfinite(reference)
    difference = values[valid] - reference[valid]
    return float(np.linalg.norm(difference) / np.linalg.norm(reference[valid]))


def fit_order(intervals: np.ndarray, errors: np.ndarray) -> float:
    """
    The order of convergence: the slope of a least-squares fit of the log of
    the errors to the log of the intervals

    Parameters
    ----------
    intervals : numpy.ndarray
        The intervals

    errors : numpy.ndarray
        The errors at those intervals, all positive

    Returns
    -------
    order : float
        The order of convergence
    """
    if np.any(errors <= 0.0):
        raise ValueError(
            f'Cannot fit an order of convergence to errors that are not all '
            f'positive: {errors}'
        )
    slope = np.polyfit(np.log(intervals), np.log(errors), 1)[0]
    return float(slope)


def select_period(
    times: np.ndarray, period_start: float, period_end: float
) -> np.ndarray:
    """
    Select the snapshots that a time mean over a period includes: those
    after the start of the period, up to and including its end

    Parameters
    ----------
    times : numpy.ndarray
        The snapshot times

    period_start : float
        The start of the period

    period_end : float
        The end of the period

    Returns
    -------
    in_period : numpy.ndarray
        Whether each snapshot is in the period
    """
    return (times > period_start) & (times <= period_end)


def relative_max_difference(
    values: np.ndarray, reference: np.ndarray
) -> float:
    """
    The largest absolute difference between two arrays relative to the
    largest absolute reference value, over the points where the reference is
    finite

    Parameters
    ----------
    values : numpy.ndarray
        The values

    reference : numpy.ndarray
        The reference values

    Returns
    -------
    difference : float
        The relative maximum difference
    """
    valid = np.isfinite(reference)
    difference = np.max(np.abs(values[valid] - reference[valid]))
    return float(difference / np.max(np.abs(reference[valid])))
