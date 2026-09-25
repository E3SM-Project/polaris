import gsw
import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf

from polaris import Step

from .month import get_month_abbreviation, get_woa23_month


class CombineStep(Step):
    """
    A step for combining a monthly and the annual WOA23 climatology.
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
            name='combine',
            subdir=subdir,
            ntasks=1,
            min_tasks=1,
        )

    @property
    def output_filename(self):
        """
        The name of the combined WOA23 file for the configured month.
        """
        month_name = get_month_abbreviation(get_woa23_month(self.config))
        return f'woa_combined_{month_name}.nc'

    def setup(self):
        """
        Set up input and output files for the step.
        """
        super().setup()
        self.add_output_file(filename=self.output_filename)

        base_url = (
            'https://www.ncei.noaa.gov/thredds-ocean/fileServer/woa23/DATA'
        )
        directories = {
            'temp': 'temperature/netcdf/decav91C0/0.25',
            'salin': 'salinity/netcdf/decav91C0/0.25',
        }
        prefixes = {'temp': 't', 'salin': 's'}

        # WOA23 numbers the annual climatology 0 and the months 1 to 12
        month = get_woa23_month(self.config)
        seasons = {'ann': 0, get_month_abbreviation(month): month}

        for field in ['temp', 'salin']:
            for season, index in seasons.items():
                woa_filename = (
                    f'woa23_decav91C0_{prefixes[field]}{index:02d}_04.nc'
                )
                woa_dir = directories[field]
                self.add_input_file(
                    filename=f'woa_{field}_{season}.nc',
                    target=woa_filename,
                    database='initial_condition_database',
                    url=f'{base_url}/{woa_dir}/{woa_filename}',
                )

    def run(self):
        """
        Combine the monthly and annual climatologies and derive conservative
        temperature and absolute salinity.
        """
        logger = self.logger
        month = get_woa23_month(self.config)
        month_name = get_month_abbreviation(month)
        logger.info(
            f'Combining the WOA23 climatology for month {month} with the '
            'annual climatology'
        )

        with xr.open_dataset('woa_temp_ann.nc', decode_times=False) as ds_temp:
            ds_out = xr.Dataset()
            for var in ['lon', 'lat', 'depth']:
                ds_out[var] = ds_temp[var]
                ds_out[f'{var}_bnds'] = ds_temp[f'{var}_bnds']

        var_map = {'temp': 't_an', 'salin': 's_an'}
        for field, var_name in var_map.items():
            with xr.open_dataset(
                f'woa_{field}_ann.nc', decode_times=False
            ) as ds_ann:
                ds_ann = ds_ann.isel(time=0, drop=True)
                with xr.open_dataset(
                    f'woa_{field}_{month_name}.nc', decode_times=False
                ) as ds_month:
                    ds_month = ds_month.isel(time=0, drop=True)
                    slices = []
                    for depth_index in range(ds_ann.sizes['depth']):
                        if depth_index < ds_month.sizes['depth']:
                            ds = ds_month
                        else:
                            ds = ds_ann
                        slices.append(ds[var_name].isel(depth=depth_index))

                    ds_out[var_name] = xr.concat(slices, dim='depth')
                    ds_out[var_name].attrs = ds_ann[var_name].attrs

        ds_out = self._to_canonical_teos10(ds_out)
        write_netcdf(ds_out, self.output_filename)
        logger.info(f'Wrote {self.output_filename}')

    @staticmethod
    def _to_canonical_teos10(ds):
        """
        Convert WOA in-situ temperature and practical salinity to canonical
        conservative temperature and absolute salinity.

        Parameters
        ----------
        ds : xarray.Dataset
            A combined WOA dataset with in-situ temperature and salinity.

        Returns
        -------
        ds : xarray.Dataset
            The dataset with conservative temperature and absolute salinity.
        """
        dims = ds.t_an.dims
        ct_slices = []
        sa_slices = []
        for depth_index in range(ds.sizes['depth']):
            temp_slice = ds.t_an.isel(depth=depth_index)
            in_situ_temp = temp_slice.values
            practical_salinity = ds.s_an.isel(depth=depth_index).values
            lat = ds.lat.broadcast_like(temp_slice).values
            lon = ds.lon.broadcast_like(temp_slice).values
            z = -ds.depth.isel(depth=depth_index).values
            pressure = gsw.p_from_z(z, lat)

            mask = np.isfinite(in_situ_temp) & np.isfinite(practical_salinity)
            conservative_temp = np.full(in_situ_temp.shape, np.nan)
            absolute_salinity = np.full(practical_salinity.shape, np.nan)
            absolute_salinity[mask] = gsw.SA_from_SP(
                practical_salinity[mask],
                pressure[mask],
                lon[mask],
                lat[mask],
            )
            conservative_temp[mask] = gsw.CT_from_t(
                absolute_salinity[mask],
                in_situ_temp[mask],
                pressure[mask],
            )
            ct_slices.append(
                xr.DataArray(
                    data=conservative_temp,
                    dims=temp_slice.dims,
                    attrs=temp_slice.attrs,
                )
            )
            sa_slices.append(
                xr.DataArray(
                    data=absolute_salinity,
                    dims=temp_slice.dims,
                    attrs=ds.s_an.attrs,
                )
            )

        ds['ct_an'] = xr.concat(ct_slices, dim='depth').transpose(*dims)
        ds.ct_an.attrs['standard_name'] = 'sea_water_conservative_temperature'
        ds.ct_an.attrs['long_name'] = (
            'Objectively analyzed mean fields for '
            'sea_water_conservative_temperature at standard depth levels.'
        )
        ds['sa_an'] = xr.concat(sa_slices, dim='depth').transpose(*dims)
        ds.sa_an.attrs['standard_name'] = 'sea_water_absolute_salinity'
        ds.sa_an.attrs['long_name'] = (
            'Objectively analyzed mean fields for '
            'sea_water_absolute_salinity at standard depth levels.'
        )
        ds.sa_an.attrs['units'] = 'g kg-1'

        return ds.drop_vars(['t_an', 's_an'])
