"""
The time series of globally integrated ocean heat content.

Heat content drift is what a coupled simulation is judged on, and it is the
one product here that is expensive on a first run and nearly free afterwards:
each month costs a read of a three-dimensional temperature field and reduces
to a handful of numbers, which the accumulator caches so that a later range
inherits them.

The integral is taken from monthly means rather than from the climatology,
because a climatology is an average over the range and a drift curve is
exactly what averaging over the range destroys.
"""

from typing import Optional

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf

from polaris.ocean.heat_content import heat_content
from polaris.ocean.model import get_layer_mass
from polaris.ocean.model.layer_mass import MASS_THICKNESS_VARIABLES
from polaris.ocean.vertical.elevation import (
    elevation_range_weights,
    is_whole_column,
    range_bound_label,
)
from polaris.tasks.ocean.analysis.accumulate import Accumulator, stamp_attrs
from polaris.tasks.ocean.analysis.analysis_step import (
    MESH_FILENAME,
    VERT_COORD_FILENAME,
)
from polaris.tasks.ocean.analysis.heat_content_config import (
    get_elevation_ranges,
    get_specific_heat,
)
from polaris.tasks.ocean.analysis.sim_files import year_range_key
from polaris.viz.style import mplstyle_context

# The version of the kernel below, which is part of the provenance stamp of
# every cached month.  Bump it whenever a month reduced here would come out
# different from one reduced by the code before the change, since that is the
# only thing standing between new code and a cache computed by old code.  The
# set of elevation ranges is in the stamp on its own, so widening what can be
# integrated is not a reason to bump this.
KERNEL_VERSION = 1

# The cache of reduced months, which is what a later range inherits, and the
# product written from it
CACHE_FILENAME = 'ocean_heat_content_cache.nc'
# named for the product alone; the publish step prefixes the group when it
# publishes it, so a name that repeats it comes out doubled
SERIES_FILENAME = 'heat_content.nc'
PLOT_FILENAME = 'heat_content.png'

# Heat content is written in J, which is the unit it means, and plotted in
# 10^22 J, which is the unit heat content budgets are quoted in and a number a
# reader can hold on to
J_PER_PLOT_UNIT = 1.0e22
PLOT_UNITS = '10$^{22}$ J'


def series_variable(label):
    """
    Get the name the series over one elevation range is stored under

    Parameters
    ----------
    label : str
        The label of the range, e.g. ``'top_to_bottom'``

    Returns
    -------
    name : str
        The variable name, e.g. ``'heat_content_top_to_bottom'``
    """
    return f'heat_content_{label}'


class HeatContentSeries(Accumulator):
    """
    A step that reduces each month of the simulation to globally integrated
    ocean heat content over a set of elevation ranges, and plots the series

    Reading a month at a time is what keeps this step's memory footprint
    independent of the length of the record, and it is what makes a month the
    unit that a later run can inherit.

    Attributes
    ----------
    mesh_path : str
        The absolute path to the mesh the cell areas come from, resolved at
        setup and part of the provenance stamp, since the areas are what the
        global integral weights by
    """

    def __init__(self, component, subdir, start_year, end_year):
        """
        Create the ocean heat content time series step

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the step belongs to

        subdir : str
            The subdirectory for the step

        start_year : int
            The first year of the time series, inclusive

        end_year : int
            The last year of the time series, inclusive
        """
        super().__init__(
            component=component,
            name='heat_content_series',
            subdir=subdir,
            start_year=start_year,
            end_year=end_year,
            cache_filename=CACHE_FILENAME,
            kernel_version=KERNEL_VERSION,
            ntasks=1,
            cpus_per_task=1,
        )
        self.mesh_path = ''
        self._area_cell: Optional[xr.DataArray] = None
        self._level_range: Optional[tuple] = None

    def setup(self):
        """
        Discover what may be inherited, and declare what is published

        The product and its plot are declared here rather than as they are
        written, because this step makes both whatever the simulation
        contains: a month it cannot reduce is an error rather than something
        to skip, since there is no other field to fall back on.
        """
        super().setup()
        self.add_output_file(SERIES_FILENAME)
        self.add_output_file(PLOT_FILENAME)

    def setup_inputs(self, sim_files):
        """
        Link the mesh and the vertical coordinate

        The mesh supplies the cell areas of the global integral and the
        vertical coordinate the indices of the top and bottom valid layer of
        each column.

        Parameters
        ----------
        sim_files : polaris.tasks.ocean.analysis.sim_files.SimulationFiles
            The files of the simulation being analyzed
        """
        self.mesh_path = sim_files.mesh_filename()
        self.add_sim_input_file(self.mesh_path, MESH_FILENAME)
        self.add_sim_input_file(
            sim_files.vert_coord_filename(), VERT_COORD_FILENAME
        )
        # so that a configuration this step can make nothing of is reported at
        # setup rather than after the monthly means have been read
        self.computed_ranges()

    def product_stamp(self):
        """
        Get the config options that decide what a reduced month contains

        The ranges here are the ones that are actually integrated rather than
        the ones that were asked for, which is what keeps a cache computed
        over the whole column alone from being inherited once every range can
        be integrated.

        Returns
        -------
        stamp : dict
            The options, as strings
        """
        ranges = self.computed_ranges()
        return {
            'elevation_ranges': ','.join(
                reduction.label for reduction in ranges
            ),
            'specific_heat': f'{get_specific_heat(self.config):.10g}',
            # the cell areas the global integral weights by come from here
            'mesh': self.mesh_path,
        }

    def computed_ranges(self):
        """
        Get the elevation ranges that can be integrated over

        Returns
        -------
        ranges : list of polaris.ocean.vertical.elevation.VerticalReduction
            The requested ranges that need no vertical geometry

        Raises
        ------
        ValueError
            If none of the requested ranges can be integrated yet
        """
        ranges = [
            reduction
            for reduction in get_elevation_ranges(self.config)
            if is_whole_column(reduction)
        ]
        if not ranges:
            raise ValueError(
                'None of the ranges in [ocean_analysis_ohc] '
                'elevation_ranges can be integrated yet, so the time series '
                'would have nothing in it.  A range with a boundary in the '
                'interior of a layer needs the vertical geometry, which is '
                'not implemented; add top:bottom, the whole column.'
            )
        return ranges

    def run(self):
        """
        Reduce the months that were not inherited, and plot the series
        """
        self._area_cell = None
        self._level_range = None
        for reduction in get_elevation_ranges(self.config):
            if not is_whole_column(reduction):
                self.logger.info(
                    f'integrating over {reduction.label} needs the vertical '
                    f'geometry, which is not implemented yet, so it is left '
                    f'out of the time series'
                )
        super().run()

    def compute_month(self, filename, year, month):
        """
        Reduce one month to the globally integrated heat content of each
        elevation range

        Only ``temperature`` and the model's mass-like thickness are read from
        the month, which is what keeps the read that dominates this step as
        small as it can be.

        Parameters
        ----------
        filename : str
            The absolute path to the monthly mean

        year : int
            The simulation year the file covers

        month : int
            The month the file covers

        Returns
        -------
        ds_month : xarray.Dataset
            One variable per elevation range, in J
        """
        config = self.config
        specific_heat = get_specific_heat(config)
        area_cell = self._get_area_cell()
        min_level_cell, max_level_cell = self._get_level_range()

        thickness = MASS_THICKNESS_VARIABLES[config.get('ocean', 'model')]
        with self.open_model_dataset(filename, config) as ds_month:
            if 'Time' in ds_month.dims:
                # a monthly mean holds one time, which the series gives back
                ds_month = ds_month.isel(Time=0)
            self._check_fields(ds_month, filename)
            # only the two fields the integral needs are read: a month of
            # global three-dimensional output is what this step's memory
            # footprint and its cost are, so reading the rest of the file
            # would be most of both
            ds = ds_month[['temperature', thickness]].load()

        temperature = ds.temperature
        layer_mass = get_layer_mass(ds, config)

        data = {}
        for reduction in self.computed_ranges():
            weights = elevation_range_weights(
                z_interface=None,
                layer_mass=layer_mass,
                min_level_cell=min_level_cell,
                max_level_cell=max_level_cell,
                z_top=reduction.z_top,
                z_bot=reduction.z_bot,
            )
            column = heat_content(temperature, weights, specific_heat)
            # a column with no mass in the range is masked rather than zero,
            # and the sum skips it, so land and cavities drop out here
            total = (area_cell * column).sum('nCells')
            total.attrs = dict(
                units='J',
                long_name=(
                    f'globally integrated ocean heat content, '
                    f'{_span(reduction)}'
                ),
                elevation_range_top=range_bound_label(reduction.z_top),
                elevation_range_bottom=range_bound_label(reduction.z_bot),
            )
            data[series_variable(reduction.label)] = total
        return xr.Dataset(data)

    def finalize(self, ds):
        """
        Write the series and plot it

        Parameters
        ----------
        ds : xarray.Dataset
            Every month of the range, in order, along a ``Time`` dimension
        """
        ds = ds.copy()
        ds['simulationYear'] = _simulation_year(ds)
        ds.attrs = dict(
            simulation_name=self.config.get(
                'ocean_analysis', 'simulation_name'
            ),
            start_year=self.start_year,
            end_year=self.end_year,
            year_range=year_range_key(self.start_year, self.end_year),
        )
        # the product carries the same stamp as the cache behind it, so that a
        # plot says what it was computed from
        ds.attrs.update(stamp_attrs(self.stamp))
        filename = self.work_path(SERIES_FILENAME)
        write_netcdf(ds=ds, fileName=filename)
        self.logger.info(f'wrote {SERIES_FILENAME}')
        self._plot(ds)

    def _plot(self, ds):
        """
        Plot the series absolutely and as an anomaly from its first month

        The two panels answer the two questions asked of heat content: how
        much there is, which is dominated by the deep ocean, and how it is
        changing, which is what a drift is and is invisible beside the
        absolute value.
        """
        ranges = self.computed_ranges()
        years = ds.simulationYear.values
        simulation_name = self.config.get('ocean_analysis', 'simulation_name')
        key = year_range_key(self.start_year, self.end_year)

        with mplstyle_context():
            figure, axes = plt.subplots(
                2, 1, sharex=True, figsize=(8.0, 7.0), layout='constrained'
            )
            for reduction in ranges:
                series = ds[series_variable(reduction.label)].values
                series = series / J_PER_PLOT_UNIT
                label = _span(reduction)
                axes[0].plot(years, series, label=label)
                axes[1].plot(years, series - series[0], label=label)
            axes[0].set_ylabel(f'heat content ({PLOT_UNITS})')
            axes[1].set_ylabel(f'anomaly ({PLOT_UNITS})')
            axes[1].set_xlabel('simulation year')
            axes[1].axhline(0.0, color='k', linewidth=0.5)
            axes[0].legend(loc='best')
            figure.suptitle(
                f'{simulation_name}: ocean heat content, years {key}'
            )
            figure.savefig(self.work_path(PLOT_FILENAME))
            plt.close(figure)
        self.logger.info(f'wrote {PLOT_FILENAME}')
        # one product, in the time series group it shares with the global
        # statistics, so both are one section of the landing page
        self.add_product(
            plot=PLOT_FILENAME,
            data=SERIES_FILENAME,
            group='time_series',
            gallery='heat_content',
            title='Ocean heat content',
            field='heat_content',
        )

    def _check_fields(self, ds, filename):
        """Report what a month is missing, rather than raising on a name"""
        model = self.config.get('ocean', 'model')
        thickness = MASS_THICKNESS_VARIABLES[model]
        missing = [
            name for name in ('temperature', thickness) if name not in ds
        ]
        if missing:
            raise ValueError(
                f'{filename} has no {", ".join(missing)}, so its heat '
                f'content cannot be computed.  Unlike a map of one field, '
                f'there is nothing else for this step to produce, so this is '
                f'an error rather than something to skip; check what the '
                f'History stream writes.'
            )

    def _get_area_cell(self):
        """The cell areas of the global integral, read once per run"""
        if self._area_cell is None:
            ds = self.read_fields(MESH_FILENAME, ['areaCell'])
            if 'areaCell' not in ds:
                raise ValueError(
                    f'The mesh {self.mesh_path} has no areaCell, without '
                    f'which heat content cannot be integrated globally.'
                )
            self._area_cell = ds.areaCell
        return self._area_cell

    def _get_level_range(self):
        """The valid layers of each column, read once per run"""
        if self._level_range is None:
            self._level_range = self.valid_level_range()
        return self._level_range


def _span(reduction):
    """How an elevation range is spelled in a label and a title"""
    return reduction.label.replace('_', ' ')


def _simulation_year(ds):
    """
    Get the time axis of the plot: the simulation year each month falls in,
    at the middle of the month

    The months are equally spaced rather than weighted by their lengths, which
    is what a time series of monthly values is plotted against and is not the
    same thing as a time average, which this product does not take.
    """
    year = ds.year.values.astype(float)
    month = ds.month.values.astype(float)
    values = year + (month - 0.5) / 12.0
    return xr.DataArray(
        np.asarray(values),
        dims='Time',
        attrs=dict(
            units='years',
            long_name='simulation year at the middle of each month',
        ),
    )
