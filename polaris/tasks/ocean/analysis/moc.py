"""
The global meridional overturning streamfunction.

Polaris does not compute the MOC.  The streamfunction needs the full
three-dimensional velocity at every time step to be right, which is why Omega
computes it in situ, and it needs the elevation of the layer interfaces it
lives on, which move.  Omega provides both as monthly means; this step
computes their annual climatology over the requested years with ``ncclimo``,
as the climatology maps are computed, and plots it.

Only the global streamfunction is plotted.  Omega's MOC group can compute the
streamfunction for named regions, and regional overturning -- the Atlantic MOC
in particular -- comes with the rest of the regional analysis later.
"""

import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf

from polaris.tasks.ocean.analysis.analysis_step import AnalysisStep
from polaris.tasks.ocean.analysis.ncclimo import (
    find_climatology_file,
    run_ncclimo,
)
from polaris.tasks.ocean.analysis.sim_files import (
    MOC_GROUP_NAME,
    year_range_key,
)
from polaris.viz import plot_lat_elevation_field
from polaris.viz.lat_elevation import MAX_CONTOUR_LINES

# The names Omega gives the fields this step reads.  A time reduction carries
# a "_TimeMean<period>" suffix on the variable whose chain was given an IOName
# and not on the coordinates, which are attached to the stream as they are, so
# both spellings are looked for and the one that was found is reported.
STREAMFUNCTION_VARIABLE = 'MOC_streamfunction_Global'
LAT_BIN_BOUNDARY_VARIABLE = 'MOCLatBinBoundaries'
INTERFACE_ELEVATION_VARIABLE = 'GeomZInterface_HorzMean'

# ``ncclimo`` computes a climatology from one file of monthly means per month,
# so that is the one kind of MOC output this step can average
MONTHLY_PERIOD = '1Month'

# Named for the region alone; the publish step prefixes the product group, so
# that these are published as moc_global_<range>
PLOT_FILENAME = 'global.png'
DATA_FILENAME = 'global.nc'

# Omega multiplies the streamfunction by 1e-6 before writing it, so the values
# are already in Sverdrups whatever the Units attribute of the field says.
# Omega forms the global streamfunction by accumulating upward-positive
# vertical volume flux from south to north, with zero at the southern
# boundary. Polaris preserves that sign: positive values describe clockwise
# overturning on a latitude-elevation plot with north to the right and
# elevation increasing upward.
STREAMFUNCTION_UNITS = 'Sv'


class Moc(AnalysisStep):
    """
    A step that computes the annual climatology of the meridional
    overturning circulation Omega computes in situ and plots it against
    latitude and elevation

    Attributes
    ----------
    has_moc_output : bool
        Whether the simulation wrote MOC output at all

    stream_problem : str or None
        Why the MOC output the simulation wrote cannot be averaged, or
        ``None`` if it can
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
        self.stream_problem = None

    def setup(self):
        """
        Link the simulation's MOC output, if it wrote any

        Omega's MOC diagnostic is new, so users will analyze simulations that
        predate it.  That is reported rather than treated as a failure, and
        the step goes on to produce nothing.
        """
        sim_files = self.get_sim_files()
        stream = sim_files.moc_stream()
        if stream is not None:
            self.stream_problem = _stream_problem(stream)
            if self.stream_problem is not None:
                self.has_moc_output = True
                return
        moc_files = sim_files.moc_files(self.start_year, self.end_year)
        self.has_moc_output = moc_files is not None
        if moc_files is None:
            return
        self.add_sim_input_files(moc_files)

    def run(self):
        """
        Compute the annual climatology of the streamfunction and its axes
        over the requested years, and plot it
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
        if self.stream_problem is not None:
            self.logger.info(self.stream_problem)
            return
        self.log_inputs()

        names = self._find_fields()
        if names is None:
            return
        run_ncclimo(self, variables=list(names), seasons=['ANN'])
        filename = find_climatology_file(self.work_path(), 'ANN')
        with xr.open_dataset(filename) as ds:
            streamfunction, lat, z = self._read_fields(ds, *names)

        write_netcdf(
            ds=self._to_dataset(streamfunction, lat, z),
            fileName=self.work_path(DATA_FILENAME),
        )
        self.logger.info(f'wrote {DATA_FILENAME}')
        self._plot(streamfunction, lat, z)

    def _find_fields(self):
        """
        Get the names of the streamfunction and its two axes in the MOC
        output, or ``None`` if the simulation did not write them all

        Returns
        -------
        names : tuple of str or None
            The streamfunction, the latitude bin boundaries and the interface
            elevations, as the files name them
        """
        filename = self.work_path(self.input_filenames[0])
        with xr.open_dataset(filename, decode_times=False) as ds:
            streamfunction = self._find(ds, STREAMFUNCTION_VARIABLE)
            boundaries = self._find(ds, LAT_BIN_BOUNDARY_VARIABLE)
            elevation = self._find(ds, INTERFACE_ELEVATION_VARIABLE)
            if (
                streamfunction is None
                or boundaries is None
                or elevation is None
            ):
                self._report_missing(ds, streamfunction, boundaries, elevation)
                return None
        return streamfunction, boundaries, elevation

    def _read_fields(self, ds, streamfunction, boundaries, elevation):
        """
        Get the climatology of the streamfunction and the axes it is plotted
        against

        Returns
        -------
        streamfunction : xarray.DataArray
            The streamfunction on (elevation, latitude)

        lat : numpy.ndarray
            The latitude of each bin center

        z : numpy.ndarray
            The elevation of each interface
        """
        lat = _bin_centers(_one_time(ds[boundaries]))
        z = np.asarray(_one_time(ds[elevation]).values, dtype=float).ravel()
        streamfunction = _orient(
            _one_time(ds[streamfunction]).load(), n_lat=len(lat), n_z=len(z)
        )
        return streamfunction, lat, z

    def _find(self, ds, base):
        """
        Find a variable under either the name a time reduction gives it or
        the name it has on its own, reporting which one was there
        """
        for name in [f'{base}_TimeMean{MONTHLY_PERIOD}', base]:
            if name in ds:
                self.logger.info(f'  read {name}')
                return name
        return None

    def _report_missing(self, ds, streamfunction, boundaries, elevation):
        """
        Say what the MOC output is missing, and what would have written it
        """
        source = self.input_filenames[0]
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
            f'disagree with the diagnostic it labels.'
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
            reduction_period=MONTHLY_PERIOD,
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

        interval = section.getfloat('contour_interval')
        drawn = plot_lat_elevation_field(
            da=streamfunction,
            lat=lat,
            z=z,
            out_filename=self.work_path(PLOT_FILENAME),
            config=config,
            colormap_section='ocean_analysis_moc',
            contour_interval=interval,
            vmin=-max_abs,
            vmax=max_abs,
            title=(
                f'{simulation_name}: global overturning streamfunction, '
                f'years {key}'
            ),
            colorbar_label=STREAMFUNCTION_UNITS,
        )
        if drawn is not None and drawn != interval:
            self.logger.info(
                f'  the streamfunction reaches {max_abs:.3g} '
                f'{STREAMFUNCTION_UNITS}, so a contour every {interval:g} '
                f'would have drawn more than {MAX_CONTOUR_LINES} lines; they '
                f'are drawn every {drawn:g} instead'
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


def _stream_problem(stream):
    """
    Say why the MOC output stream cannot be averaged, or ``None`` if it can
    """
    if (
        stream.is_reduction
        and stream.period == MONTHLY_PERIOD
        and '$M' in stream.filename
    ):
        return None
    kind = 'time-mean' if stream.is_reduction else 'snapshot'
    return (
        f'The {MOC_GROUP_NAME} analysis group writes {stream.filename}, a '
        f'{stream.period} {kind} stream.  The MOC climatology is computed '
        f'with ncclimo from one file of monthly means per month, as the '
        f'climatology maps are, so the group needs ReductionPeriod: '
        f'[{MONTHLY_PERIOD}] and a Filename with $Y and $M in it to make this '
        f'plot.'
    )


def _one_time(da):
    """
    Drop the time dimension of a climatology, which has one time

    The latitude bin boundaries are written without one, and come through
    ``ncclimo`` without one too.
    """
    if 'time' in da.dims:
        return da.isel(time=0)
    return da


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
