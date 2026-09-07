"""
The global meridional overturning streamfunction.

Polaris does not compute the MOC.  The streamfunction needs the full
three-dimensional velocity at every time step to be right, which is why Omega
computes it in situ, and it needs the elevation of the layer interfaces it
lives on, which move.  Omega provides both; this step averages the reductions
Omega wrote over the requested years and plots them.

Only the global streamfunction is plotted.  Omega's MOC group can compute the
streamfunction for named regions, and regional overturning -- the Atlantic MOC
in particular -- comes with the rest of the regional analysis later.
"""

import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf

from polaris.tasks.ocean.analysis.analysis_step import AnalysisStep
from polaris.tasks.ocean.analysis.sim_files import (
    MOC_GROUP_NAME,
    year_range_key,
)
from polaris.viz import plot_lat_elevation_field

# The names Omega gives the fields this step reads.  A time reduction carries
# a "_TimeMean<period>" suffix on the variable whose chain was given an IOName
# and not on the coordinates, which are attached to the stream as they are, so
# both spellings are looked for and the one that was found is reported.
STREAMFUNCTION_VARIABLE = 'MOC_streamfunction_Global'
LAT_BIN_BOUNDARY_VARIABLE = 'MOCLatBinBoundaries'
INTERFACE_ELEVATION_VARIABLE = 'GeomZInterface_HorzMean'

# Named for the region alone; the publish step prefixes the product group, so
# that these are published as moc_global_<range>
PLOT_FILENAME = 'global.png'
DATA_FILENAME = 'global.nc'

# Omega multiplies the streamfunction by 1e-6 before writing it, so the values
# are already in Sverdrups whatever the Units attribute of the field says
STREAMFUNCTION_UNITS = 'Sv'


class Moc(AnalysisStep):
    """
    A step that time averages the meridional overturning circulation Omega
    computes in situ and plots it against latitude and elevation

    Attributes
    ----------
    has_moc_output : bool
        Whether the simulation wrote MOC output at all

    reduction_period : str or None
        The period Omega reduced the streamfunction over, or ``None`` if it
        wrote snapshots.  The variables are named differently in the two
        cases, and the two are averaged differently, so which one it is has
        to be known before the file is opened.
    """

    def __init__(self, component, subdir, start_year, end_year):
        """
        Create the MOC step

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the step belongs to

        subdir : str
            The subdirectory for the step

        start_year : int
            The first year to average over, inclusive

        end_year : int
            The last year to average over, inclusive
        """
        super().__init__(
            component=component,
            name='moc',
            subdir=subdir,
            start_year=start_year,
            end_year=end_year,
            ntasks=1,
            cpus_per_task=1,
        )
        self.has_moc_output = False
        self.reduction_period = None

    def setup(self):
        """
        Link the simulation's MOC output, if it wrote any

        Omega's MOC diagnostic is new, so users will analyze simulations that
        predate it.  That is reported rather than treated as a failure, and
        the step goes on to produce nothing.
        """
        sim_files = self.get_sim_files()
        moc_files = sim_files.moc_files(self.start_year, self.end_year)
        self.has_moc_output = moc_files is not None
        if moc_files is None:
            return
        self.add_sim_input_files(moc_files)
        stream = sim_files.moc_stream()
        assert stream is not None
        self.reduction_period = stream.period if stream.is_reduction else None

    def run(self):
        """
        Average the streamfunction over the requested years and plot it
        """
        if not self.has_moc_output:
            self.logger.info(
                f'The simulation wrote no MOC output, so there is nothing '
                f'to plot.  Polaris does not compute the overturning '
                f'streamfunction: it needs the full three-dimensional '
                f'velocity at every time step, which is why Omega computes '
                f'it in situ.  Turn on the {MOC_GROUP_NAME} analysis group '
                f'in the simulation and run it again to get this plot.'
            )
            return
        self.log_inputs()

        with self._open_moc() as ds:
            fields = self._read_fields(ds)
        if fields is None:
            return
        streamfunction, lat, z = fields

        write_netcdf(
            ds=self._to_dataset(streamfunction, lat, z),
            fileName=self.work_path(DATA_FILENAME),
        )
        self.logger.info(f'wrote {DATA_FILENAME}')
        self._plot(streamfunction, lat, z)

    def _open_moc(self):
        """
        Open the MOC output over the requested years as one series

        The variables keep the names Omega gave them, since those are the
        names this step looks for.
        """
        ds = xr.open_mfdataset(
            [self.work_path(filename) for filename in self.input_filenames],
            combine='nested',
            concat_dim='time',
            # the latitude bin boundaries are the same in every file and
            # carry no time dimension, so they are taken from the first file
            # rather than given one
            data_vars='minimal',
            coords='minimal',
            compat='override',
        )
        if 'time' in ds.dims:
            # the rest of Polaris spells the time dimension the MPAS-Ocean way
            ds = ds.rename({'time': 'Time'})
        return ds

    def _read_fields(self, ds):
        """
        Get the time-averaged streamfunction and the axes it is plotted
        against, or ``None`` if the simulation did not write them all

        Returns
        -------
        fields : tuple or None
            The streamfunction as a :py:class:`xarray.DataArray`, the
            latitude of each bin and the elevation of each interface
        """
        streamfunction = self._find(ds, STREAMFUNCTION_VARIABLE)
        boundaries = self._find(ds, LAT_BIN_BOUNDARY_VARIABLE)
        elevation = self._find(ds, INTERFACE_ELEVATION_VARIABLE)
        if streamfunction is None or boundaries is None or elevation is None:
            self._report_missing(ds, streamfunction, boundaries, elevation)
            return None

        weights = self._weights(ds)
        streamfunction = _weighted_time_mean(ds[streamfunction], weights)
        elevation = _weighted_time_mean(ds[elevation], weights)

        lat = _bin_centers(ds[boundaries].values)
        z = np.asarray(elevation.values, dtype=float).ravel()
        streamfunction = _orient(streamfunction, n_lat=len(lat), n_z=len(z))
        return streamfunction, lat, z

    def _find(self, ds, base):
        """
        Find a variable under either the name a time reduction gives it or
        the name it has on its own, reporting which one was there
        """
        candidates = [base]
        if self.reduction_period is not None:
            candidates.insert(0, f'{base}_TimeMean{self.reduction_period}')
        for name in candidates:
            if name in ds:
                self.logger.info(f'  read {name}')
                return name
        return None

    def _weights(self, ds):
        """
        Get the weight of each time in the average

        The streamfunction is linear in the velocity, so a mean of the
        reductions weighted by the length of each period is the
        streamfunction of the mean flow over the whole range.  Monthly
        periods differ in length by up to a tenth, so this is not a
        formality.

        Snapshots cover no period, so they are averaged with equal weights
        and the log says so.
        """
        if self.reduction_period is None:
            self.logger.info(
                '  the MOC output holds snapshots rather than time means, '
                'so they are averaged with equal weights'
            )
            return xr.ones_like(ds.Time, dtype=float)
        days = period_lengths(ds)
        self.logger.info(
            f'  averaging {len(days)} {self.reduction_period} reductions, '
            f'weighted by periods of {days.min():g} to {days.max():g} days'
        )
        return xr.DataArray(days, dims=('Time',))

    def _report_missing(self, ds, streamfunction, boundaries, elevation):
        """
        Say what the MOC output is missing, and what would have written it

        The capability is new in Omega, so a file that predates part of it is
        an ordinary case: the step reports it and makes nothing, rather than
        raising from inside a lookup.
        """
        source = ', '.join(self.input_filenames)
        if streamfunction is None:
            self.logger.info(
                f'{source} has no {STREAMFUNCTION_VARIABLE}, which is what '
                f'the {MOC_GROUP_NAME} analysis group writes for the Global '
                f'region.  It holds: {_variable_list(ds)}.'
            )
            return
        missing = []
        if boundaries is None:
            missing.append(f'{LAT_BIN_BOUNDARY_VARIABLE}, the latitude axis')
        if elevation is None:
            missing.append(
                f'{INTERFACE_ELEVATION_VARIABLE}, the elevation axis'
            )
        self.logger.info(
            f'{source} has the streamfunction but not {" or ".join(missing)}.'
            f'  Omega attaches both to every {MOC_GROUP_NAME} output stream, '
            f'so a simulation that predates that writes the streamfunction '
            f'alone.  Polaris does not reconstruct them: the interfaces move, '
            f'and an axis averaged over a different period would quietly '
            f'disagree with the diagnostic it labels.  Re-run the simulation '
            f'with a newer Omega to get this plot.'
        )

    def _to_dataset(self, streamfunction, lat, z):
        """Assemble exactly what is plotted, so it can be checked again"""
        ds = xr.Dataset()
        ds['mocStreamfunction'] = xr.DataArray(
            streamfunction.values,
            dims=('nVertInterfaces', 'nLatBins'),
            attrs=dict(
                units=STREAMFUNCTION_UNITS,
                long_name=(
                    'global meridional overturning streamfunction, time '
                    'averaged over the range'
                ),
            ),
        )
        ds['latBinCenter'] = xr.DataArray(
            lat,
            dims=('nLatBins',),
            attrs=dict(
                units='degrees_north',
                long_name='latitude of the center of each MOC bin',
            ),
        )
        ds['zInterface'] = xr.DataArray(
            z,
            dims=('nVertInterfaces',),
            attrs=dict(
                units='m',
                long_name=(
                    'mean elevation of each layer interface, positive up, as '
                    'the model reported it over the same period'
                ),
            ),
        )
        ds.attrs = dict(
            simulation_name=self.config.get(
                'ocean_analysis', 'simulation_name'
            ),
            region='Global',
            start_year=self.start_year,
            end_year=self.end_year,
            year_range=year_range_key(self.start_year, self.end_year),
            reduction_period=(
                'none; these are snapshots'
                if self.reduction_period is None
                else self.reduction_period
            ),
            source_files=', '.join(self.input_filenames),
        )
        return ds

    def _plot(self, streamfunction, lat, z):
        """Plot the streamfunction and describe it in the manifest"""
        config = self.config
        section = config['ocean_analysis_moc']
        if section.has_option('max_streamfunction'):
            max_abs = section.getfloat('max_streamfunction')
        else:
            # centered on zero and scaled to the data, so that the two
            # circulation cells are the two colors of the map
            max_abs = float(np.nanmax(np.abs(streamfunction.values)))
        simulation_name = config.get('ocean_analysis', 'simulation_name')
        key = year_range_key(self.start_year, self.end_year)

        plot_lat_elevation_field(
            da=streamfunction,
            lat=lat,
            z=z,
            out_filename=self.work_path(PLOT_FILENAME),
            config=config,
            colormap_section='ocean_analysis_moc',
            contour_interval=section.getfloat('contour_interval'),
            max_abs=max_abs,
            title=(
                f'{simulation_name}: global overturning streamfunction, '
                f'years {key}'
            ),
            colorbar_label=STREAMFUNCTION_UNITS,
        )
        self.logger.info(f'wrote {PLOT_FILENAME}')

        # The outputs are registered here rather than in setup() because a
        # simulation that wrote no MOC output, or wrote it without its axes,
        # makes neither, and a step that had declared them at setup would
        # fail on the missing files instead of reporting what it found.
        for filename in (PLOT_FILENAME, DATA_FILENAME):
            self.add_produced_file(filename)
        # one gallery per region, so that regional overturning adds galleries
        # to this group rather than a group of its own
        self.add_product(
            plot=PLOT_FILENAME,
            data=DATA_FILENAME,
            group='moc',
            gallery='global',
            title='Global meridional overturning streamfunction',
            region='Global',
        )


def period_lengths(ds):
    """
    Get the length in days of the period each time reduction covers

    Omega stamps a reduction with a single time rather than with the bounds of
    the period it covers, so the length of a period is the interval between
    one stamp and the next, and the first period is given the length of the
    second.  That is exact for periods of a fixed length and out by the
    difference between two adjacent months for the first of a series of
    monthly means -- at most three days in a record of hundreds, and confined
    to one end of it.

    Parameters
    ----------
    ds : xarray.Dataset
        The MOC output, with a decoded ``Time`` coordinate

    Returns
    -------
    days : numpy.ndarray
        The length of each period, in days
    """
    gaps = _days_between(ds.Time.values)
    if gaps.size == 0:
        # one reduction carries the whole average, so its weight cancels
        return np.ones(ds.sizes.get('Time', 1))
    return np.concatenate([gaps[:1], gaps])


def _days_between(times):
    """
    Get the number of days between consecutive times

    Only the intervals are wanted, so this asks nothing of the time
    coordinate beyond being ordered and subtractable -- no CF units, no
    reference date, and the same answer for a file straight from the model as
    for one that has been read and written again.
    """
    times = np.asarray(times)
    if times.size < 2:
        return np.zeros(0)
    if np.issubdtype(times.dtype, np.datetime64):
        return np.diff(times) / np.timedelta64(1, 'D')
    # cftime dates, which subtract to a datetime.timedelta
    return np.array(
        [
            (late - early).total_seconds() / 86400.0
            for early, late in zip(times[:-1], times[1:], strict=True)
        ]
    )


def _weighted_time_mean(da, weights):
    """
    Average a field over time, skipping what is below the seafloor

    ``weighted`` renormalizes by the weights of the values that are there, so
    a column that is missing from some of the reductions is averaged over the
    ones it appears in rather than coming out as a NaN.
    """
    if 'Time' not in da.dims:
        return da
    return da.weighted(weights).mean('Time')


def _bin_centers(boundaries):
    """
    Get the center of each latitude bin

    Omega writes the boundaries, one more of them than there are bins, since
    that is what a bin is defined by.  Contouring is defined at points, so it
    wants the centers.
    """
    boundaries = np.asarray(boundaries, dtype=float).ravel()
    return 0.5 * (boundaries[:-1] + boundaries[1:])


def _orient(da, n_lat, n_z):
    """
    Put the streamfunction on (elevation, latitude), whatever order Omega
    wrote its dimensions in

    The dimensions are matched by size rather than by name, since their names
    come from the operator chain that produced them and would change with it.
    """
    sizes = {dim: da.sizes[dim] for dim in da.dims}
    lat_dims = [dim for dim, size in sizes.items() if size == n_lat]
    z_dims = [dim for dim, size in sizes.items() if size == n_z]
    if len(da.dims) != 2 or not lat_dims or not z_dims:
        raise ValueError(
            f'The streamfunction has dimensions {sizes}, which do not '
            f'match {n_lat} latitude bins and {n_z} layer interfaces.  The '
            f'latitude bins come from {LAT_BIN_BOUNDARY_VARIABLE} and the '
            f'interfaces from {INTERFACE_ELEVATION_VARIABLE}, so one of the '
            f'three does not belong to the others.'
        )
    if n_lat == n_z:
        # nothing in the sizes tells them apart, and Omega writes latitude
        # first, so the array is transposed to put elevation down the rows
        return da.transpose(*da.dims[::-1])
    return da.transpose(z_dims[0], lat_dims[0])


def _variable_list(ds):
    """The variables in a file, for an error message"""
    names = sorted(str(name) for name in ds.data_vars)
    return ', '.join(names) if names else 'nothing'
