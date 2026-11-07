import zipfile

import netCDF4
import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf

from polaris import Step
from polaris.landice.mismip_plus.geometry import DOMAIN_WIDTH
from polaris.tasks.landice.mismip_plus.experiments import EXPERIMENTS

# the supplement to Cornford et al. (2020) on Zenodo, under CC-BY-4.0
SUPPLEMENT_URL = (
    'https://zenodo.org/records/3611936/files/supplement.zip?download=1'
)

# MALI's own entry, made in 2017
MALI_2017_ENTRY = 'MHO_MPASLI_HO_Weertman_500m'

# the farthest (m) from the centerline that a submitted grounding-line point
# may be to give the grounding line's position there
CENTERLINE_TOLERANCE = 1.0e3


class Cornford2020(Step):
    """
    A step for downloading the results submitted to MISMIP+ (Cornford et al.
    2020) and gathering them for each experiment
    """

    def __init__(self, component, indir):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        indir : str
            the directory the step is in, to which ``name`` will be appended
        """
        super().__init__(component=component, name='cornford2020', indir=indir)
        self.add_input_file(
            filename='supplement.zip',
            target='cornford2020_supplement.zip',
            database='mismip_plus',
            url=SUPPLEMENT_URL,
        )
        for experiment in EXPERIMENTS:
            self.add_output_file(filename=f'{experiment.name}.nc')

    def run(self):
        """
        Run this step
        """
        with zipfile.ZipFile('supplement.zip') as archive:
            members = [
                name
                for name in archive.namelist()
                if name.startswith('submission_data/') and name.endswith('.nc')
            ]
            for experiment in EXPERIMENTS:
                prefix = f'submission_data/{experiment.name}_'
                entries = dict()
                for name in sorted(members):
                    if not name.startswith(prefix):
                        continue
                    entry = name[len(prefix) : -len('.nc')]
                    entries[entry] = archive.read(name)
                ds = _gather_entries(entries)
                write_netcdf(ds, f'{experiment.name}.nc')


def _gather_entries(entries):
    """
    Gather the time series of the entries for one experiment, padded with
    NaNs to a common length, along with the grounding line of MALI's entry
    """
    series = {
        entry: _read_entry(contents) for entry, contents in entries.items()
    }
    names = list(series.keys())
    n_time = max(len(entry['time']) for entry in series.values())

    ds = xr.Dataset()
    ds['entry'] = ('entry', np.array(names, dtype=str))
    ds['weertman'] = (
        'entry',
        np.array(['Weertman' in name for name in names]),
    )
    for var in ['time', 'iceVolume', 'iceVAF', 'groundedArea', 'xGL']:
        values = np.nan * np.ones((len(names), n_time))
        for index, name in enumerate(names):
            entry_values = series[name][var]
            values[index, : len(entry_values)] = entry_values
        ds[var] = (('entry', 'nTime'), values)

    if MALI_2017_ENTRY in entries:
        x_gl, y_gl = _read_grounding_line(entries[MALI_2017_ENTRY])
        ds['mali2017XGL'] = (('nPointGL', 'nTimeMali2017'), x_gl)
        ds['mali2017YGL'] = (('nPointGL', 'nTimeMali2017'), y_gl)
    return ds


def _read_entry(contents):
    """
    Read the time series of one entry, and its grounding line's position on
    the centerline
    """
    with netCDF4.Dataset('entry.nc', memory=contents) as ds:
        series = dict()
        series['time'] = _read(ds, 'time')
        series['iceVolume'] = _read(ds, 'iceVolume')
        series['groundedArea'] = _read(ds, 'groundedArea')
        # some entries spell it iceVaf
        vaf_name = 'iceVAF' if 'iceVAF' in ds.variables else 'iceVaf'
        series['iceVAF'] = _read(ds, vaf_name)
    x_gl, y_gl = _read_grounding_line(contents)
    series['xGL'] = _centerline_position(x_gl, y_gl)
    return series


def _read_grounding_line(contents):
    """
    Read the points of an entry's grounding line, with time as the second
    dimension
    """
    with netCDF4.Dataset('entry.nc', memory=contents) as ds:
        n_time = len(ds.variables['time'])
        x_gl = _read(ds, 'xGL')
        y_gl = _read(ds, 'yGL')
    if x_gl.shape[1] != n_time and x_gl.shape[0] == n_time:
        x_gl = x_gl.T
        y_gl = y_gl.T
    return x_gl, y_gl


def _centerline_position(x_gl, y_gl):
    """
    The most upstream grounding-line point near the centerline at each time
    """
    near = np.abs(y_gl - 0.5 * DOMAIN_WIDTH) <= CENTERLINE_TOLERANCE
    x_near = np.where(near, x_gl, np.nan)
    position = np.nan * np.ones(x_gl.shape[1])
    has_points = np.any(np.isfinite(x_near), axis=0)
    position[has_points] = np.nanmin(x_near[:, has_points], axis=0)
    return position


def _read(ds, var):
    """
    Read a variable as floats with NaN where it is masked
    """
    values = ds.variables[var][:]
    return np.ma.filled(np.ma.asarray(values, dtype=float), np.nan)
