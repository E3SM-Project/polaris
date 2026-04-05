import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf
from scipy.signal import convolve2d

from polaris import Step


class ExtrapolateStep(Step):
    """
    A step for extrapolating WOA23 into missing ocean, land and ice regions.
    """

    output_filename = 'woa23_decav_0.25_jan_extrap.nc'

    def __init__(self, component, subdir, combine_step, combine_topo_step):
        """
        Create the step.

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to.

        subdir : str
            The subdirectory for the step.

        combine_step : polaris.Step
            The step that produces the combined WOA23 dataset.

        combine_topo_step : polaris.Step
            The cached ``e3sm/init`` step that produces combined topography on
            the WOA23 grid.
        """
        super().__init__(
            component=component,
            name='extrapolate',
            subdir=subdir,
            ntasks=1,
            min_tasks=1,
        )
        self.combine_step = combine_step
        self.combine_topo_step = combine_topo_step
        self.add_output_file(filename=self.output_filename)

    def setup(self):
        """
        Set up input files for the step.
        """
        super().setup()
        self.add_input_file(
            filename='woa.nc',
            work_dir_target=f'{self.combine_step.path}/woa_combined.nc',
        )
        self.add_input_file(
            filename='topography.nc',
            work_dir_target=(
                f'{self.combine_topo_step.path}/'
                f'{self.combine_topo_step.combined_filename}'
            ),
        )

    def run(self):
        """
        Extrapolate WOA23 horizontally and vertically in two stages.
        """
        logger = self.logger
        logger.info('Building a 3D ocean mask on the WOA23 grid')
        self._make_3d_ocean_mask()

        logger.info('Horizontally extrapolating within the ocean mask')
        self._extrap_horiz(
            in_filename='woa.nc',
            out_filename='woa_extrap_ocean_horiz.nc',
            use_ocean_mask=True,
        )

        logger.info('Vertically extrapolating within the ocean mask')
        self._extrap_vert(
            in_filename='woa_extrap_ocean_horiz.nc',
            out_filename='woa_extrap_ocean.nc',
            use_ocean_mask=True,
        )

        logger.info('Horizontally extrapolating into land and grounded ice')
        self._extrap_horiz(
            in_filename='woa_extrap_ocean.nc',
            out_filename='woa_extrap_horiz.nc',
            use_ocean_mask=False,
        )

        logger.info('Vertically extrapolating into land and grounded ice')
        self._extrap_vert(
            in_filename='woa_extrap_horiz.nc',
            out_filename=self.output_filename,
            use_ocean_mask=False,
        )
        logger.info(f'Wrote {self.output_filename}')

    @staticmethod
    def _make_3d_ocean_mask():
        """
        Build a three-dimensional mask of valid ocean cells on the WOA grid.
        """
        with xr.open_dataset('topography.nc') as ds_topo:
            with xr.open_dataset('woa.nc', decode_times=False) as ds_woa:
                ds_out = xr.Dataset()
                for var in ['lon', 'lat', 'depth']:
                    ds_out[var] = ds_woa[var]
                    ds_out[f'{var}_bnds'] = ds_woa[f'{var}_bnds']

                z_top = -ds_woa.depth_bnds.isel(nbounds=0)
                ocean_mask = ExtrapolateStep._get_ocean_mask(ds_topo)
                ocean_mask_3d = (
                    (ds_topo.base_elevation <= z_top) & (ocean_mask >= 0.5)
                ).transpose('depth', 'lat', 'lon')
                ds_out['ocean_mask'] = ocean_mask_3d.astype(np.int8)

        write_netcdf(ds_out, 'ocean_mask.nc')

    @staticmethod
    def _get_ocean_mask(ds_topo):
        """
        Return the 2D ocean mask from combined topography.
        """
        return ds_topo.ocean_mask

    def _extrap_horiz(self, in_filename, out_filename, use_ocean_mask):
        """
        Extrapolate horizontally on each depth level.

        Parameters
        ----------
        in_filename : str
            The input file to read.

        out_filename : str
            The output file to write.

        use_ocean_mask : bool
            Whether to restrict filling to the remapped ocean mask.
        """
        with xr.open_dataset(in_filename, decode_times=False) as ds:
            ds_out = ds.load()

        ocean_mask = None
        if use_ocean_mask:
            with xr.open_dataset('ocean_mask.nc') as ds_mask:
                ocean_mask = ds_mask.ocean_mask.values.astype(bool)

        ndepth = ds_out.sizes['depth']
        for depth_index in range(ndepth):
            self.logger.info(
                f'  Horizontal fill for depth {depth_index + 1}/{ndepth}'
            )
            level_mask = None
            if ocean_mask is not None:
                level_mask = ocean_mask[depth_index, :, :]
            ds_level = ds_out.isel(depth=depth_index)
            ds_level = self._extrap_level(
                ds_level=ds_level,
                ocean_mask=level_mask,
                threshold=self.config.getfloat('woa23', 'extrap_threshold'),
            )
            for field_name in ['pt_an', 's_an']:
                ds_out[field_name][depth_index, :, :] = ds_level[field_name]

        write_netcdf(ds_out, out_filename)

    def _extrap_vert(self, in_filename, out_filename, use_ocean_mask):
        """
        Extrapolate vertically from shallower depths into deeper missing
        values.

        Parameters
        ----------
        in_filename : str
            The input file to read.

        out_filename : str
            The output file to write.

        use_ocean_mask : bool
            Whether to restrict filling to the remapped ocean mask.
        """
        with xr.open_dataset(in_filename, decode_times=False) as ds:
            ds_out = ds.load()

        ocean_mask = None
        if use_ocean_mask:
            with xr.open_dataset('ocean_mask.nc') as ds_mask:
                ocean_mask = ds_mask.ocean_mask.values.astype(bool)

        ndepth = ds_out.sizes['depth']
        for field_name in ['pt_an', 's_an']:
            field = ds_out[field_name].values
            for depth_index in range(1, ndepth):
                mask = np.isnan(field[depth_index, :, :])
                if ocean_mask is not None:
                    mask = np.logical_and(mask, ocean_mask[depth_index, :, :])
                field[depth_index, :, :][mask] = field[depth_index - 1, :, :][
                    mask
                ]

        write_netcdf(ds_out, out_filename)

    @staticmethod
    def _extrap_level(ds_level, ocean_mask, threshold):
        """
        Extrapolate a single depth level horizontally.

        Parameters
        ----------
        ds_level : xarray.Dataset
            A single-depth WOA dataset.

        ocean_mask : numpy.ndarray or None
            A Boolean mask for valid ocean cells at this depth.

        threshold : float
            The minimum valid weight sum needed to mark a new cell valid.

        Returns
        -------
        ds_level : xarray.Dataset
            The filled depth level.
        """
        kernel = ExtrapolateStep._get_kernel()
        field = ds_level.pt_an.values

        valid = np.isfinite(field)
        orig_mask = valid.copy()
        if ocean_mask is not None:
            invalid_after_fill = np.logical_not(
                np.logical_or(valid, ocean_mask)
            )
        else:
            invalid_after_fill = None

        fields = {
            field_name: ds_level[field_name].values.copy()
            for field_name in ['pt_an', 's_an']
        }

        nlon = field.shape[1]
        lon_with_halo = np.array(
            [nlon - 2, nlon - 1] + list(range(nlon)) + [0, 1]
        )
        lon_no_halo = list(range(2, nlon + 2))

        prev_fill_count = 0
        while True:
            valid_weight_sum = _extrap_with_halo(
                field=valid.astype(float),
                kernel=kernel,
                valid=valid,
                lon_with_halo=lon_with_halo,
                lon_no_halo=lon_no_halo,
            )
            if invalid_after_fill is not None:
                valid_weight_sum[invalid_after_fill] = 0.0

            new_valid = valid_weight_sum > threshold
            fill_mask = np.logical_and(new_valid, np.logical_not(orig_mask))
            fill_count = int(np.count_nonzero(fill_mask))
            if fill_count == prev_fill_count:
                break

            for _field_name, field_values in fields.items():
                field_extrap = _extrap_with_halo(
                    field=field_values,
                    kernel=kernel,
                    valid=valid,
                    lon_with_halo=lon_with_halo,
                    lon_no_halo=lon_no_halo,
                )
                field_values[fill_mask] = (
                    field_extrap[fill_mask] / valid_weight_sum[fill_mask]
                )

            valid = new_valid
            prev_fill_count = fill_count

        for field_name, field_values in fields.items():
            if invalid_after_fill is not None:
                field_values[invalid_after_fill] = np.nan
            ds_level[field_name] = (ds_level[field_name].dims, field_values)

        return ds_level

    @staticmethod
    def _get_kernel():
        """
        Build the small averaging kernel used for horizontal extrapolation.

        Returns
        -------
        kernel : numpy.ndarray
            A two-dimensional Gaussian-like averaging kernel.
        """
        coordinates = np.arange(-1, 2)
        x, y = np.meshgrid(coordinates, coordinates)
        return np.exp(-0.5 * (x**2 + y**2))


def _extrap_with_halo(field, kernel, valid, lon_with_halo, lon_no_halo):
    """
    Extrapolate a two-dimensional field using a periodic halo in longitude.

    Parameters
    ----------
    field : numpy.ndarray
        The field to extrapolate.

    kernel : numpy.ndarray
        The horizontal averaging kernel.

    valid : numpy.ndarray
        A Boolean mask of valid values.

    lon_with_halo : numpy.ndarray
        Longitude indices including the periodic halo.

    lon_no_halo : list of int
        Longitude indices excluding the periodic halo.

    Returns
    -------
    field_extrap : numpy.ndarray
        The convolved field without the periodic halo.
    """
    masked_field = field.copy()
    masked_field[np.logical_not(valid)] = 0.0
    field_with_halo = masked_field[:, lon_with_halo]
    field_extrap = convolve2d(field_with_halo, kernel, mode='same')
    return field_extrap[:, lon_no_halo]
