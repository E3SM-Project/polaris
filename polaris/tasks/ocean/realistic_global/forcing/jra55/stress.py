import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf

from polaris import Step

JRA55_STRESS_FILENAME = 'jra55_stress.nc'

# JRA55-do is published as one file per variable per year of 3-hourly
# instantaneous ("3hrPt") data on the TL319 grid
_TABLE_ID = '3hrPt'
_GRID_LABEL = 'gr'
_MIP_TEMPLATE = (
    '{var}_input4MIPs_atmosphericState_OMIP_{source_id}_{grid}_'
    '{year}01010000-{year}12312100.nc'
)


class Jra55StressStep(Step):
    """
    A step for deriving a time-invariant global wind-stress product from
    JRA55-do 10-m winds.

    The stress is computed at every 3-hourly step and then time-averaged,
    rather than computing the stress of the time-mean wind.  Averaging the
    wind first would discard the gust contribution and underestimate the
    stress in the storm tracks, which is the reason the 3-hourly data is
    needed at all.

    The reduction itself is quick, but it needs several GiB of raw
    reanalysis, so the derived product is distributed through the Polaris
    cache and this step is ``default_cached``.  The standalone
    :py:class:`.Jra55` task overrides that to regenerate the product.
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
            name='stress',
            subdir=subdir,
            ntasks=1,
            min_tasks=1,
        )
        self.add_output_file(filename=JRA55_STRESS_FILENAME)
        # The reduction itself is quick, but it needs ~3.5 GiB of raw winds
        # that would otherwise have to be downloaded on every machine, so
        # the product is cached and this step reads it from the cache
        # database unless a task asks for it to run (see the Jra55 task).
        self.default_cached = True

    def setup(self):
        """
        Declare the raw JRA55-do wind files, whose URLs are built from config.
        """
        super().setup()
        section = self.config['jra55']
        base_url = section.get('base_url')
        source_id = section.get('source_id')
        version = section.get('version')
        year = section.getint('year')

        for var in ['uas', 'vas']:
            filename = _MIP_TEMPLATE.format(
                var=var,
                source_id=source_id,
                grid=_GRID_LABEL,
                year=year,
            )
            url = (
                f'{base_url}/{source_id}/atmos/{_TABLE_ID}/{var}/'
                f'{_GRID_LABEL}/{version}/{filename}'
            )
            self.add_input_file(
                filename=f'{var}.nc',
                target=filename,
                database='initial_condition_database',
                url=url,
            )

    def run(self):
        """
        Average the wind stress over the configured month and write the
        product.
        """
        logger = self.logger
        section = self.config['jra55']
        year = section.getint('year')
        month = section.getint('month')
        rho_air = section.getfloat('rho_air')
        min_wind_speed = section.getfloat('min_wind_speed')
        chunk_size = section.getint('time_chunk_size')

        logger.info(
            f'Averaging JRA55-do wind stress over {year}-{month:02d} '
            f'(this reads two ~1.8 GiB files)'
        )

        # JRA55-do time units are "days since 1900-01-01" on a non-standard
        # calendar, so decode to cftime rather than numpy datetimes
        time_coder = xr.coders.CFDatetimeCoder(use_cftime=True)
        with (
            xr.open_dataset('uas.nc', decode_times=time_coder) as ds_u,
            xr.open_dataset('vas.nc', decode_times=time_coder) as ds_v,
        ):
            time_index = np.flatnonzero(
                (ds_u.time.dt.year == year).values
                & (ds_u.time.dt.month == month).values
            )
            if time_index.size == 0:
                raise ValueError(
                    f'No JRA55-do time slices found for {year}-{month:02d}'
                )
            logger.info(f'Found {time_index.size} time slices')

            taux_sum, tauy_sum = self._accumulate_stress(
                ds_u=ds_u,
                ds_v=ds_v,
                time_index=time_index,
                rho_air=rho_air,
                min_wind_speed=min_wind_speed,
                chunk_size=chunk_size,
            )
            count = float(time_index.size)
            ds_out = self._build_dataset(
                ds_u=ds_u,
                taux=taux_sum / count,
                tauy=tauy_sum / count,
            )

        ds_out.attrs['source_id'] = section.get('source_id')
        ds_out.attrs['source_version'] = section.get('version')
        ds_out.attrs['time_window'] = f'{year}-{month:02d}'
        ds_out.attrs['n_time_slices'] = time_index.size
        ds_out.attrs['drag_law'] = (
            'Large and Yeager (2004, 2009) neutral 10-m drag: '
            '1e3*Cd = 2.70/U + 0.142 + 0.0764*U; '
            f'rho_air = {rho_air} kg m-3; '
            f'wind speed clamped below at {min_wind_speed} m s-1'
        )
        ds_out.attrs['averaging'] = (
            'stress computed at each 3-hourly step, then time-averaged'
        )

        write_netcdf(ds_out, JRA55_STRESS_FILENAME)
        logger.info(f'Wrote {JRA55_STRESS_FILENAME}')

    def _accumulate_stress(
        self, ds_u, ds_v, time_index, rho_air, min_wind_speed, chunk_size
    ):
        """
        Sum the wind stress over the selected time slices, a chunk at a time.

        A month of 3-hourly TL319 winds is 248 x 320 x 640 per component, so
        the time loop is chunked rather than loaded whole.
        """
        taux_sum = None
        tauy_sum = None
        for start in range(0, time_index.size, chunk_size):
            chunk = time_index[start : start + chunk_size]
            u10 = ds_u.uas.isel(time=chunk).values
            v10 = ds_v.vas.isel(time=chunk).values
            taux, tauy = wind_stress(
                u10=u10,
                v10=v10,
                rho_air=rho_air,
                min_wind_speed=min_wind_speed,
            )
            if taux_sum is None:
                taux_sum = taux.sum(axis=0)
                tauy_sum = tauy.sum(axis=0)
            else:
                taux_sum += taux.sum(axis=0)
                tauy_sum += tauy.sum(axis=0)
        assert taux_sum is not None and tauy_sum is not None
        return taux_sum, tauy_sum

    @staticmethod
    def _build_dataset(ds_u, taux, tauy):
        """
        Assemble the output dataset on the native TL319 grid.

        The grid is deliberately **not** padded, in latitude or longitude.
        Bilinear remapping is center-based for ESMF but corner-based for
        mbtempest, and padding a lat-lon source so that either its corners or
        its centers reach the pole aborts mbtempest with "Unable to find a
        face that contains the point".  Duplicating a longitude column breaks
        both tools, because pyremap reconstructs corners from centers and the
        grid then spans 365 degrees and overlaps itself; it is also
        unnecessary, since TL319's longitude corners already span exactly 360
        degrees.  The small residual polar cap is filled after remapping
        instead.  See remap_bilinear_pole_findings.md.
        """
        ds_out = xr.Dataset()
        for var in ['lat', 'lon']:
            ds_out[var] = ds_u[var]
            bnds = f'{var}_bnds'
            if bnds in ds_u:
                ds_out[bnds] = ds_u[bnds]

        dims = ('lat', 'lon')
        ds_out['taux'] = xr.DataArray(
            data=taux,
            dims=dims,
            attrs={
                'units': 'N m-2',
                'long_name': 'zonal surface wind stress',
                'standard_name': 'surface_downward_eastward_stress',
            },
        )
        ds_out['tauy'] = xr.DataArray(
            data=tauy,
            dims=dims,
            attrs={
                'units': 'N m-2',
                'long_name': 'meridional surface wind stress',
                'standard_name': 'surface_downward_northward_stress',
            },
        )
        return ds_out


def wind_stress(u10, v10, rho_air, min_wind_speed):
    """
    Compute wind stress from 10-m winds with the Large and Yeager (2004,
    2009) neutral drag law.

    The stability correction, the ocean-current-relative wind and any
    sea-ice drag distinction are deliberately omitted; they are second-order
    for spinning down fast waves.

    Parameters
    ----------
    u10, v10 : numpy.ndarray
        Zonal and meridional 10-m wind components (m s-1)

    rho_air : float
        Air density (kg m-3)

    min_wind_speed : float
        Wind speeds below this value (m s-1) are clamped, since the 2.70/U
        term in the drag law diverges as the wind speed goes to zero

    Returns
    -------
    taux, tauy : numpy.ndarray
        Zonal and meridional wind stress (N m-2)
    """
    speed = np.maximum(np.sqrt(u10**2 + v10**2), min_wind_speed)
    drag = 1e-3 * (2.70 / speed + 0.142 + 0.0764 * speed)
    factor = rho_air * drag * speed
    return factor * u10, factor * v10
