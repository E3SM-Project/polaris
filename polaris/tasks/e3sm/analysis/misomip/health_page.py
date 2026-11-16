import numpy as np
import xarray as xr

from polaris.analysis.page import PageStep
from polaris.e3sm.analysis.calendar import days_to_date
from polaris.tasks.e3sm.analysis.misomip.diagnostics import (
    RUN_HEALTH_FILENAME,
)

#: The most fast cells listed for a day
LISTED_SPIKE_CELLS = 5


class RunHealthPage(PageStep):
    """
    A step that makes a page of the checks of a run's health, as tables:
    the days a cell is very fast, the salt above anything the run starts
    with or restores to each year, and the dry columns under the ice at the
    start of each year
    """

    def __init__(self, component, subdir, diagnostics, kind, label):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory for the step

        diagnostics : RunDiagnostics
            The diagnostics step of the run, which computes the checks

        kind : {'e3sm', 'standalone'}
            The kind of run

        label : str
            The run's label in the page's title
        """
        super().__init__(
            component=component,
            name=f'{kind}_run_health',
            subdir=subdir,
            ntasks=1,
            cpus_per_task=1,
            page_name=f'{kind}_run_health',
            page_title=f'Health of the {label} run',
        )
        self.add_input_file(
            filename=RUN_HEALTH_FILENAME,
            work_dir_target=f'{diagnostics.path}/{RUN_HEALTH_FILENAME}',
        )
        self.add_dependency(diagnostics)

    def run(self):
        """
        Write the page from the diagnostics' checks
        """
        # the times are days, not dates to decode
        with xr.open_dataset(
            RUN_HEALTH_FILENAME, decode_times=False, decode_timedelta=False
        ) as ds:
            add_health_sections(self.page, ds.load())
        self.write_page()


def add_health_sections(page, ds):
    """
    Add the checks of a run's health to a page

    Parameters
    ----------
    page : polaris.analysis.page.Page
        The page

    ds : xarray.Dataset
        The checks, as the diagnostics write them
    """
    _add_spikes(page, ds)
    _add_salt(page, ds)
    _add_dry_cells(page, ds)


def _add_spikes(page, ds):
    """The days with a fast cell"""
    title = 'Fast cells'
    speed = ds.attrs['spike_speed']
    if not ds.attrs['has_custom']:
        page.add_section(
            title, text='The run wrote no daily maxima of kinetic energy.'
        )
        return
    text = (
        f'The days on which the speed of the largest kinetic energy at a '
        f'cell center, √(2 KE) of the daily maximum, is above {speed:g} '
        f"m/s.  Cells are 0-based, with x and y in km in the protocol's "
        f'coordinates, fastest first.'
    )
    days = ds.spikeDay.values if 'spikeDay' in ds else np.array([])
    if days.size == 0:
        page.add_section(
            title, text=f'No cell was faster than {speed:g} m/s on any day.'
        )
        return
    rows = []
    for day in np.unique(days):
        on_day = np.flatnonzero(days == day)
        on_day = on_day[np.argsort(-ds.spikeSpeed.values[on_day])]
        cells = [
            _cell_text(ds, 'spike', index)
            + f' {ds.spikeSpeed.values[index]:.2f} m/s'
            for index in on_day[:LISTED_SPIKE_CELLS]
        ]
        if len(on_day) > LISTED_SPIKE_CELLS:
            cells.append(f'and {len(on_day) - LISTED_SPIKE_CELLS} more')
        rows.append(
            [
                days_to_date(day),
                f'{ds.spikeSpeed.values[on_day[0]]:.2f}',
                str(len(on_day)),
                '; '.join(cells),
            ]
        )
    page.add_section(
        title,
        text=text,
        table=dict(
            columns=['Day', 'Peak (m/s)', 'Fast cells', 'Cells'],
            rows=rows,
        ),
    )


def _add_salt(page, ds):
    """The salt above the source maximum, the largest month of each year"""
    source_max = ds.attrs['source_max_salinity']
    text = [
        f'Salinity above the largest the run starts with or restores to, '
        f'S_max = {source_max:.3f} PSU, as the largest monthly mean of each '
        f'year.  A salty cell has a layer more than 0.1 PSU above S_max.',
        f'The excess salt is the sum of the area times the layer thickness '
        f'times S − S_max over the layers above S_max, in PSU km³: within '
        f'{1e-3 * ds.attrs["salt_near_distance"]:g} km of a partly floating '
        f'cell, near the grounding line; under the rest of the ice shelf; '
        f'and beyond the ice front at x = '
        f'{1e-3 * ds.attrs["ice_front_x"]:g} km.',
    ]
    years = np.floor(ds.time.values).astype(int)
    rows = []
    for year in np.unique(years):
        ds_year = ds.isel(Time=np.flatnonzero(years == year))
        rows.append(
            [
                f'{year:04d}',
                _signed(float(ds_year.maxSalinityExcess.max())),
                str(int(ds_year.saltyCells.max())),
                f'{float(ds_year.saltExcessNearGroundingLine.max()):.3f}',
                f'{float(ds_year.saltExcessUnderShelf.max()):.3f}',
                f'{float(ds_year.saltExcessBeyondFront.max()):.3f}',
            ]
        )
    page.add_section(
        'Salt above the source',
        text=text,
        table=dict(
            columns=[
                'Year',
                'Max S − S_max (PSU)',
                'Salty cells',
                'Near the grounding line',
                'Under the shelf',
                'Beyond the front',
            ],
            rows=rows,
        ),
    )


def _add_dry_cells(page, ds):
    """The census of dry columns at each state"""
    title = 'Dry columns'
    if 'dryTime' not in ds:
        page.add_section(title, text='The run has no states to check.')
        return
    min_thickness = ds.attrs['min_thickness']
    density = ds.attrs['land_ice_ocean_density']
    text = (
        f'The columns with every layer at the minimum thickness of wetting '
        f'and drying, {min_thickness:g} m, give or take 10%, at the start of '
        f"each year and the end of the last.  A column's deficit is the "
        f'column its land-ice pressure calls for, the bottom depth less the '
        f"pressure over {density:g} kg/m³ times MPAS's gravity, less its "
        f'actual column.  The largest positive deficits are listed, as '
        f"0-based cells with x and y in km in the protocol's coordinates."
    )
    thresholds = ds.deficitThreshold.values
    rows = []
    for index in range(ds.sizes['nDryStates']):
        ds_state = ds.isel(nDryStates=index)
        counts = [
            str(int(count)) for count in ds_state.dryCellsWithDeficit.values
        ]
        max_deficit = float(ds_state.maxDryDeficit)
        largest = [
            _cell_text(ds_state, 'largestDeficit', slot)
            + f' {ds_state.largestDeficit.values[slot]:.2f} m'
            for slot in range(ds_state.sizes['nLargestDeficits'])
            if ds_state.largestDeficitCell.values[slot] >= 0
        ]
        rows.append(
            [days_to_date(float(ds_state.dryTime))]
            + [str(int(ds_state.dryCells))]
            + counts
            + [
                '' if np.isnan(max_deficit) else f'{max_deficit:.2f}',
                '; '.join(largest),
            ]
        )
    page.add_section(
        title,
        text=text,
        table=dict(
            columns=['Date', 'Dry columns']
            + [f'Deficit > {threshold:g} m' for threshold in thresholds]
            + ['Largest deficit (m)', 'Largest deficits'],
            rows=rows,
        ),
    )


def _cell_text(ds, prefix, index):
    """A cell as its 0-based index and its x and y (km)"""
    cell = int(ds[f'{prefix}Cell'].values[index])
    x = float(ds[f'{prefix}X'].values[index])
    y = float(ds[f'{prefix}Y'].values[index])
    return f'{cell} ({x:.1f}, {y:.1f})'


def _signed(value):
    """A value with its sign to 3 decimals, without a negative zero"""
    return f'{round(value, 3) + 0.0:+.3f}'
