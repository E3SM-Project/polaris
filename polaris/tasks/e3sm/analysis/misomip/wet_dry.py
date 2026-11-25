"""
Where MPAS-Ocean treats its cells as wet or dry, from its year-start
restarts and, where it writes them, its monthly means of the barotropic
flow's wetting flag on each edge
"""

from typing import NamedTuple

import netCDF4
import numpy as np

from polaris.e3sm.analysis.calendar import days_to_date, xtime_to_days
from polaris.tasks.e3sm.analysis.misomip.runs import (
    SNAPSHOT_STREAM,
)

#: The classes of cell, in the order of their colors
GROUNDED, DRY, IN_BETWEEN, WET = range(4)

#: The class labels, for the legend
WET_DRY_LABELS = [
    'grounded: under ice the ocean and MALI treat as grounded (no melt)',
    'dry: every edge closed to flow',
    'in between: some edges closed, or closed for part of the month',
    'wet: no edge closed',
]

#: The class colors
WET_DRY_COLORS = ['#b0b0b0', '#8c510a', '#f6a01a', '#9ecae1']

#: How the title names a state from a year-start restart and one from a
#: monthly mean
YEAR_START_KIND = 'year-start snapshot'
MONTHLY_KIND = 'monthly'

#: The wetting flag of the barotropic flow on each edge: 1 open, 0 closed
WETTING_FLAG = 'wettingVelocityBarotropicSubcycle'

#: The restart stream of the ocean
RESTART_STREAM = 'restart'

#: How far a monthly mean may be from 0 or 1 and still count as closed or
#: open the whole month
TOLERANCE = 1e-6


class WetDryStates(NamedTuple):
    """
    Which cells are grounded, dry, in between or wet, at each of the times
    the analysis knows it

    Attributes
    ----------
    start_days : numpy.ndarray
        When each state starts to hold, in days since 0001-01-01: the start
        of a year for a restart, the start of a month for a monthly mean.
        Each holds until the next.

    labels : list of str
        Each state's time and kind, for a panel's title

    classes : numpy.ndarray
        The class of each cell in each state, ``GROUNDED``, ``DRY``,
        ``IN_BETWEEN`` or ``WET``
    """

    start_days: np.ndarray
    labels: list
    classes: np.ndarray

    @property
    def has_year_start(self):
        """Whether any state comes from a year-start restart"""
        return any(label.startswith(YEAR_START_KIND) for label in self.labels)

    @property
    def has_monthly(self):
        """Whether any state comes from a monthly mean"""
        return any(label.startswith(MONTHLY_KIND) for label in self.labels)

    def state_at(self, day):
        """
        Get the state holding on a day

        Parameters
        ----------
        day : float
            The day, in days since 0001-01-01

        Returns
        -------
        index : int or None
            The state, or ``None`` before the first
        """
        index = int(np.searchsorted(self.start_days, day + 1e-6)) - 1
        return None if index < 0 else index


def get_wet_dry_caption(states):
    """
    Describe the panel of wet and dry cells for the caption, by the kinds
    of state it shows

    Parameters
    ----------
    states : WetDryStates
        The states

    Returns
    -------
    caption : str
        Where the states come from and what the classes mean
    """
    sources = []
    if states.has_year_start:
        sources.append(
            'from the restart at the start of each year, held until the next'
        )
    if states.has_monthly:
        sources.append(
            'each month, from the mean over the month of whether each edge '
            'is open'
        )
    caption = (
        "Below the melt, where the ocean's barotropic flow is closed by "
        f'wetting and drying: {", and then ".join(sources)}. A cell is dry '
        'where every edge is closed to barotropic flow, and grounded where '
        "the ocean's floating mask is 0 under land ice: the ice draft lies "
        "below the sea floor and MALI's floating fraction is 0, so the cell "
        'exchanges no melt or heat with the ice.'
    )
    if states.has_monthly:
        caption = (
            f'{caption} In a monthly frame, the grounded cells are those at '
            'the start of the month.'
        )
    return caption


def classify_cells(
    open_fraction,
    cells_on_edge,
    edges_on_cell,
    n_edges_on_cell,
    grounded,
):
    """
    Classify cells by how open to barotropic flow their active edges are

    Parameters
    ----------
    open_fraction : numpy.ndarray
        Each edge's wetting flag, 1 open and 0 closed, or its monthly mean,
        the fraction of the month it was open

    cells_on_edge, edges_on_cell : numpy.ndarray
        The mesh's connectivity, numbered from 1, with 0 for none

    n_edges_on_cell : numpy.ndarray
        The number of edges of each cell

    grounded : numpy.ndarray
        Whether each cell is grounded

    Returns
    -------
    classes : numpy.ndarray
        Each cell's class: ``GROUNDED``; ``DRY`` where every active edge is
        closed; ``WET`` where none is ever closed; ``IN_BETWEEN`` otherwise
    """
    active = np.all(cells_on_edge > 0, axis=1)
    slots = np.arange(edges_on_cell.shape[1])[np.newaxis, :]
    valid = slots < n_edges_on_cell[:, np.newaxis]
    edges = np.where(valid, edges_on_cell - 1, 0)
    counted = valid & active[edges]
    fraction = open_fraction[edges]
    any_closed = np.any(counted & (fraction < 1.0 - TOLERANCE), axis=1)
    all_closed = np.all(~counted | (fraction <= TOLERANCE), axis=1)
    has_active = np.any(counted, axis=1)
    classes = np.full(len(n_edges_on_cell), IN_BETWEEN, dtype=np.int8)
    classes[~any_closed] = WET
    classes[all_closed & has_active] = DRY
    classes[grounded] = GROUNDED
    return classes


def find_wet_dry_inputs(run, monthly, start_year, end_year):
    """
    Find the files a run's wet and dry cells are read from, if it wets and
    dries

    Parameters
    ----------
    run : polaris.e3sm.analysis.runs.E3smRun or StandaloneRun
        The run

    monthly : list of polaris.streams.StreamFile
        The run's monthly means in the years analyzed

    start_year, end_year : int
        The years analyzed

    Returns
    -------
    inputs : dict of str to list of str
        The restarts at the start of each year analyzed, the monthly means
        and the month-start snapshots, by kind, or empty lists for a run
        without wetting and drying
    """
    inputs: dict = dict(restarts=[], monthly=[], snapshots=[])
    try:
        wets_and_dries = run.namelist_option('config_use_wetting_drying')
    except (OSError, ValueError, KeyError):
        return inputs
    if wets_and_dries.strip().lower() not in ['.true.', 'true']:
        return inputs
    try:
        restarts = run.find_stream_files(RESTART_STREAM)
    except ValueError:
        restarts = []
    inputs['restarts'] = [
        stream_file.path
        for stream_file in restarts
        if start_year <= stream_file.year <= end_year
        and (stream_file.month, stream_file.day, stream_file.seconds)
        == (1, 1, 0)
    ]
    inputs['monthly'] = [stream_file.path for stream_file in monthly]
    try:
        snapshots = run.find_stream_files(SNAPSHOT_STREAM)
    except ValueError:
        snapshots = []
    inputs['snapshots'] = [
        stream_file.path
        for stream_file in snapshots
        if start_year <= stream_file.year <= end_year + 1
    ]
    return inputs


def read_wet_dry_states(
    ds_init, restart_filenames, monthly_filenames, snapshot_filenames
):
    """
    Read which cells are grounded, dry, in between or wet: from the
    restarts at the start of each year, until the monthly means hold the
    wetting flag, and from those after

    Parameters
    ----------
    ds_init : xarray.Dataset
        The ocean's initial condition and mesh

    restart_filenames : list of str
        The restarts at the start of each year, in order

    monthly_filenames : list of str
        The monthly means, in order

    snapshot_filenames : list of str
        The month-start snapshots, in order, which may hold the ocean's
        land-ice masks

    Returns
    -------
    states : WetDryStates or None
        The states, or ``None`` if no file holds the wetting flag

    Notes
    -----
    A monthly state's grounded cells are those at the start of its month,
    from the snapshot then or, for want of one, the restart, while its wet
    and dry cells come from the wetting flag's mean over the month
    """
    mesh = dict(
        cells_on_edge=ds_init.cellsOnEdge.values,
        edges_on_cell=ds_init.edgesOnCell.values,
        n_edges_on_cell=ds_init.nEdgesOnCell.values,
    )
    masks = _index_masks(restart_filenames + snapshot_filenames)
    monthly = _read_monthly_states(monthly_filenames, masks, mesh)
    first_month = monthly[0][0] if monthly else np.inf
    states = []
    for filename in restart_filenames:
        with netCDF4.Dataset(filename) as nc:
            if WETTING_FLAG not in nc.variables:
                continue
            day = float(xtime_to_days(_char_string(nc, 'xtime', 0)))
            if day >= first_month:
                continue
            open_flag = np.asarray(nc.variables[WETTING_FLAG][0, :])
        grounded = _grounded_at(masks, day)
        if grounded is None:
            continue
        classes = classify_cells(open_flag, grounded=grounded, **mesh)
        states.append(
            (day, f'{YEAR_START_KIND}, {days_to_date(day)}', classes)
        )
    states.extend(monthly)
    if not states:
        return None
    states.sort(key=lambda state: state[0])
    return WetDryStates(
        start_days=np.array([state[0] for state in states]),
        labels=[state[1] for state in states],
        classes=np.array([state[2] for state in states]),
    )


def _read_monthly_states(monthly_filenames, masks, mesh):
    """The states from the monthly means with the wetting flag, until the
    first month without the land-ice masks at its start"""
    flag = f'timeMonthly_avg_{WETTING_FLAG}'
    # the monthly means with the flag are the last ones, since the run
    # started writing it partway through
    with_flag = []
    for filename in reversed(monthly_filenames):
        with netCDF4.Dataset(filename) as nc:
            if flag not in nc.variables:
                break
        with_flag.append(filename)
    with_flag.reverse()
    states = []
    for filename in with_flag:
        with netCDF4.Dataset(filename) as nc:
            # the mean starts after the month's first time step, so its
            # month is taken from its start and the state from the month's
            # first instant, when the snapshot or restart has the masks
            month = _char_string(nc, 'xtime_startMonthly', 0)[:7]
            start = float(xtime_to_days(f'{month}-01_00:00:00'))
            open_fraction = np.asarray(nc.variables[flag][0, :])
        grounded = _grounded_at(masks, start)
        if grounded is None:
            # without the masks, a cell can't be called grounded, so the
            # monthly states stop here
            break
        classes = classify_cells(open_fraction, grounded=grounded, **mesh)
        states.append(
            (start, f'{MONTHLY_KIND}, {days_to_date(start)[:7]}', classes)
        )
    return states


def _index_masks(filenames):
    """The file and record of each snapshot or restart that holds the
    ocean's land-ice masks, by its time"""
    index: dict = dict()
    for filename in filenames:
        with netCDF4.Dataset(filename) as nc:
            if not all(
                name in nc.variables
                for name in ['landIceMask', 'landIceFloatingMask', 'xtime']
            ):
                continue
            for record in range(len(nc.dimensions['Time'])):
                day = float(xtime_to_days(_char_string(nc, 'xtime', record)))
                index.setdefault(round(day, 3), (filename, record))
    return index


def _grounded_at(masks, day):
    """The cells grounded at a time, if a snapshot or restart has the
    masks then: land ice that does not float"""
    found = masks.get(round(day, 3))
    if found is None:
        return None
    filename, record = found
    with netCDF4.Dataset(filename) as nc:
        mask = np.asarray(nc.variables['landIceMask'][record, :])
        floating = np.asarray(nc.variables['landIceFloatingMask'][record, :])
    return (mask == 1) & (floating == 0)


def _char_string(nc, name, record):
    """A string from a character variable of a netCDF file"""
    variable = nc.variables[name]
    variable.set_auto_chartostring(False)
    chars = np.ma.filled(variable[record, :], b' ')
    return b''.join(chars).decode().strip()
