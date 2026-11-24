import netCDF4
import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf

from polaris import Step
from polaris.cf import add_cf_conventions

SHORTWAVE_EXTINCTION_FILENAME = 'shortwave_extinction.nc'

GMIS_FILL = -9999.0

# Manizza et al. (2005) coefficients: k = k0 + a * Chl ** p
RED = (0.225, 0.037, 0.629)
BLUE = (0.0232, 0.074, 0.674)

SOLAR_CONSTANT = 1361.0
DAYS_PER_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


class ShortwaveExtinctionProductStep(Step):
    """
    A step for building annual, insolation-weighted red- and blue-band
    shortwave extinction coefficients from the GMIS monthly chlorophyll-a
    climatology.

    For each month, the coefficients follow Manizza et al. (2005):

    .. code-block:: text

        k_red  = 0.225  + 0.037 * Chl ** 0.629
        k_blue = 0.0232 + 0.074 * Chl ** 0.674

    with chlorophyll in mg m-3, capped at ``max_chl``.  The monthly
    coefficients are averaged with weights given by the monthly-mean
    top-of-atmosphere daily insolation at each latitude, normalized at each
    point over only the months with valid data.  Points with no valid month
    are given the coefficients for a constant chlorophyll, ``fill_chl``.

    The product is on the native 1/12-degree GMIS grid and the 12 monthly
    files are downloaded into the Polaris database.  The options are in the
    ``[gmis_extinction]`` config section.
    """

    def __init__(self, component, subdir):
        """
        Create the step.

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to.

        subdir : str
            The subdirectory for the step.
        """
        super().__init__(
            component=component,
            name='extinction_product',
            subdir=subdir,
            ntasks=1,
            min_tasks=1,
        )
        self.add_output_file(filename=SHORTWAVE_EXTINCTION_FILENAME)
        self.add_cf_check(SHORTWAVE_EXTINCTION_FILENAME)

    def setup(self):
        """
        Declare the monthly GMIS files, whose URLs are built from config.
        """
        super().setup()
        section = self.config['gmis_extinction']
        base_url = section.get('base_url')
        sensor = section.get('sensor')
        for month in range(1, 13):
            filename = _gmis_filename(sensor, month)
            self.add_input_file(
                filename=filename,
                target=filename,
                database='initial_condition_database',
                url=f'{base_url}/{filename}',
            )

    def run(self):
        """
        Compute the product from the monthly chlorophyll and write it.
        """
        section = self.config['gmis_extinction']
        sensor = section.get('sensor')
        max_chl = section.getfloat('max_chl')
        fill_chl = section.getfloat('fill_chl')
        if not np.isfinite(max_chl) or max_chl <= 0.0:
            raise ValueError('[gmis_extinction] max_chl must be positive')
        if not np.isfinite(fill_chl) or fill_chl < 0.0:
            raise ValueError('[gmis_extinction] fill_chl must be nonnegative')

        filenames = [_gmis_filename(sensor, month) for month in range(1, 13)]
        ds = compute_extinction(
            filenames, max_chl=max_chl, fill_chl=fill_chl, logger=self.logger
        )
        ds.attrs['source'] = (
            f'GMIS 9 km monthly chlorophyll-a climatology (JRC), sensor '
            f'{sensor}, {section.get("base_url")}'
        )
        write_netcdf(add_cf_conventions(ds), SHORTWAVE_EXTINCTION_FILENAME)


def compute_extinction(filenames, max_chl, fill_chl, logger=None):
    """
    Compute annual, insolation-weighted shortwave extinction coefficients
    from 12 monthly GMIS chlorophyll-a files.

    Parameters
    ----------
    filenames : list of str
        The 12 monthly GMIS files, January first

    max_chl : float
        The cap (mg m-3) applied to monthly chlorophyll before computing the
        coefficients

    fill_chl : float
        The chlorophyll (mg m-3) used at points with no valid month

    logger : logging.Logger, optional
        A logger for progress messages

    Returns
    -------
    ds : xarray.Dataset
        The coefficients on the GMIS grid, with latitude ascending
    """
    if len(filenames) != 12:
        raise ValueError(f'Expected 12 monthly files, got {len(filenames)}')

    lat, lon = _read_grid(filenames[0])
    shape = (lat.size, lon.size)
    insolation = monthly_insolation(lat)

    sum_w = np.zeros(shape)
    sum_red = np.zeros(shape)
    sum_blue = np.zeros(shape)
    sum_chl = np.zeros(shape)
    n_valid = np.zeros(shape, dtype=np.int8)

    for month, filename in enumerate(filenames, start=1):
        month_lat, month_lon = _read_grid(filename)
        if not (
            np.array_equal(lat, month_lat) and np.array_equal(lon, month_lon)
        ):
            raise ValueError(
                f'GMIS grid does not match the first month: {filename}'
            )
        chl, valid = _read_chl(filename)
        w = np.where(valid, insolation[month - 1][:, None], 0.0)
        chl = np.where(valid, np.minimum(chl, max_chl), 0.0)
        sum_w += w
        sum_red += w * _manizza(chl, RED)
        sum_blue += w * _manizza(chl, BLUE)
        sum_chl += w * chl
        n_valid += valid
        if logger is not None:
            logger.info(f'month {month:02d}: {valid.mean():.3f} valid')

    # points with valid data only in months of zero insolation have no
    # meaningful weight and are treated as missing
    has_data = sum_w > 0.0
    denom = np.where(has_data, sum_w, 1.0)
    fields = {
        'ExtinctionCoeffRed': (sum_red / denom, _manizza(fill_chl, RED)),
        'ExtinctionCoeffBlue': (sum_blue / denom, _manizza(fill_chl, BLUE)),
        'ChlorophyllWeighted': (sum_chl / denom, fill_chl),
    }
    if logger is not None:
        logger.info(f'{has_data.mean():.3f} of points have data')

    # write with latitude ascending, as most remapping tools expect
    flip = lat[0] > lat[-1]
    if flip:
        lat = lat[::-1]
        n_valid = n_valid[::-1]
        has_data = has_data[::-1]

    attrs = {
        'ExtinctionCoeffRed': {
            'long_name': 'red-band shortwave extinction coefficient',
            'units': 'm-1',
        },
        'ExtinctionCoeffBlue': {
            'long_name': 'blue-band shortwave extinction coefficient',
            'units': 'm-1',
        },
        'ChlorophyllWeighted': {
            'long_name': 'insolation-weighted annual mean surface '
            'chlorophyll-a',
            'units': 'mg m-3',
        },
    }

    ds = xr.Dataset()
    ds['lat'] = xr.DataArray(
        lat,
        dims='lat',
        attrs={
            'standard_name': 'latitude',
            'units': 'degrees_north',
            'axis': 'Y',
        },
    )
    ds['lon'] = xr.DataArray(
        lon,
        dims='lon',
        attrs={
            'standard_name': 'longitude',
            'units': 'degrees_east',
            'axis': 'X',
        },
    )
    for name, (field, fill_value) in fields.items():
        if flip:
            field = field[::-1]
        ds[name] = xr.DataArray(
            np.where(has_data, field, fill_value).astype(np.float32),
            dims=('lat', 'lon'),
            attrs=attrs[name],
        )
    ds['nValidMonths'] = xr.DataArray(
        n_valid,
        dims=('lat', 'lon'),
        attrs={'long_name': 'number of months with valid GMIS chlorophyll'},
    )
    ds['filled'] = xr.DataArray(
        (~has_data).astype(np.int8),
        dims=('lat', 'lon'),
        attrs={
            'long_name': 'whether the point had no valid month and was filled',
            'flag_values': np.array([0, 1], dtype=np.int8),
            'flag_meanings': 'computed filled',
        },
    )
    ds.attrs['title'] = (
        'Shortwave extinction coefficients from GMIS chlorophyll-a'
    )
    ds.attrs['method'] = (
        f'Monthly Chl capped at {max_chl} mg m-3; monthly k = k0 + a * '
        f'Chl**p (Manizza et al. 2005; red 0.225, 0.037, 0.629; blue '
        f'0.0232, 0.074, 0.674), averaged with monthly-mean TOA daily '
        f'insolation weights normalized per point over valid months; '
        f'points without valid data filled with Chl = {fill_chl} mg m-3'
    )
    ds.attrs['references'] = (
        'Manizza, M., C. Le Quere, A. J. Watson, and E. T. Buitenhuis '
        '(2005), Bio-optical feedbacks among phytoplankton, upper ocean '
        'physics and sea-ice in a global model, Geophys. Res. Lett., 32, '
        'L05603, doi:10.1029/2004GL020778'
    )
    return ds


def monthly_insolation(lat):
    """
    Monthly mean of the daily-mean top-of-atmosphere insolation (W m-2) as a
    function of latitude, averaged over every day of a 365-day year.

    Parameters
    ----------
    lat : numpy.ndarray
        Latitude in degrees

    Returns
    -------
    numpy.ndarray
        Insolation with shape (12, lat.size)
    """
    phi = np.deg2rad(lat)[None, :]
    doy = np.arange(1, 366)[:, None]
    gamma = 2.0 * np.pi * (doy - 1) / 365.0
    # Spencer (1971) declination and Earth-Sun distance factor
    decl = (
        0.006918
        - 0.399912 * np.cos(gamma)
        + 0.070257 * np.sin(gamma)
        - 0.006758 * np.cos(2 * gamma)
        + 0.000907 * np.sin(2 * gamma)
        - 0.002697 * np.cos(3 * gamma)
        + 0.00148 * np.sin(3 * gamma)
    )
    dist = (
        1.000110
        + 0.034221 * np.cos(gamma)
        + 0.001280 * np.sin(gamma)
        + 0.000719 * np.cos(2 * gamma)
        + 0.000077 * np.sin(2 * gamma)
    )
    h0 = np.arccos(np.clip(-np.tan(phi) * np.tan(decl), -1.0, 1.0))
    daily = (
        SOLAR_CONSTANT
        / np.pi
        * dist
        * (
            h0 * np.sin(phi) * np.sin(decl)
            + np.cos(phi) * np.cos(decl) * np.sin(h0)
        )
    )
    bounds = np.cumsum([0] + DAYS_PER_MONTH)
    return np.array(
        [daily[bounds[m] : bounds[m + 1]].mean(axis=0) for m in range(12)]
    )


def _gmis_filename(sensor, month):
    return f'GMIS_{sensor}_CHLA_{month:02d}.nc'


def _read_grid(filename):
    with netCDF4.Dataset(filename) as ds:
        lat = ds['lat'][:].astype(float)
        lon = ds['lon'][:].astype(float)
    for name, coord in [('latitude', lat), ('longitude', lon)]:
        if (
            coord.ndim != 1
            or coord.size < 2
            or not np.isfinite(coord).all()
            or not (np.all(np.diff(coord) > 0) or np.all(np.diff(coord) < 0))
        ):
            raise ValueError(
                f'GMIS {name} must be finite and strictly monotonic'
            )
    if np.any(np.abs(lat) > 90):
        raise ValueError('GMIS latitude must be between -90 and 90 degrees')
    if lon[0] > lon[-1]:
        raise ValueError('GMIS longitude must be ascending')
    return lat, lon


def _read_chl(filename):
    """Read GMIS log10 chlorophyll, returning Chl (mg m-3) and validity."""
    with netCDF4.Dataset(filename) as ds:
        ds.set_auto_mask(False)
        var = ds['Chl_a']
        if var.getncattr('scalling') != 'log10':
            raise ValueError(f'Unexpected Chl_a scaling in {filename}')
        if var.dimensions != ('lat', 'lon'):
            raise ValueError(f'Unexpected Chl_a dimensions in {filename}')
        log_chl = var[:].astype(float)
    valid = (log_chl != GMIS_FILL) & np.isfinite(log_chl)
    chl = np.where(valid, 10.0 ** np.where(valid, log_chl, 0.0), np.nan)
    return chl, valid


def _manizza(chl, coeffs):
    k0, a, p = coeffs
    return k0 + a * chl**p
