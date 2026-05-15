import os

import numpy as np
import xarray as xr
from scipy import ndimage

from polaris.mesh.spherical.coastline import (
    CONVENTIONS,
    _write_netcdf_with_fill_values,
)
from polaris.mesh.spherical.unified.resolutions import FINEST_RESOLUTION
from polaris.step import Step

__all__ = ['RemapCoastlineStep']


class RemapCoastlineStep(Step):
    """
    Remap coastline products from the finest lat-lon grid to a coarser one.

    The ocean mask is remapped conservatively (block average) and thresholded.
    Connectivity is inherited from the flood-filled finest-resolution mask, so
    no second flood fill is performed.  The signed distance is remapped
    bilinearly (as an unsigned magnitude) and then re-signed using the
    remapped ocean mask.
    """

    def __init__(
        self,
        component,
        fine_coastline_step,
        coarse_resolution,
        subdir,
    ):
        """
        Create a new step.

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        fine_coastline_step : ComputeCoastlineStep
            The shared highest-resolution coastline step whose outputs are
            remapped to the coarser grid

        coarse_resolution : float
            The target coarser lat-lon resolution in degrees

        subdir : str
            The subdirectory within the component's work directory
        """
        super().__init__(
            component=component,
            name='coastline_remap',
            subdir=subdir,
            cpus_per_task=1,
            min_cpus_per_task=1,
        )
        self.default_cached = True
        self.fine_coastline_step = fine_coastline_step
        self.fine_resolution = FINEST_RESOLUTION
        self.coarse_resolution = coarse_resolution
        self.output_filenames = {
            convention: f'coastline_{convention}.nc'
            for convention in CONVENTIONS
        }

    def setup(self):
        """
        Set up the step in the work directory, including linking inputs.
        """
        fine_step = self.fine_coastline_step
        for filename in fine_step.output_filenames.values():
            self.add_input_file(
                filename=f'fine_{filename}',
                work_dir_target=os.path.join(fine_step.path, filename),
            )
        for filename in self.output_filenames.values():
            self.add_output_file(filename=filename)

    def run(self):
        """
        Run this step.
        """
        section = self.config['coastline']
        mask_threshold = section.getfloat('mask_threshold')
        fine_resolution = self.fine_resolution
        coarse_resolution = self.coarse_resolution

        scale = _compute_scale(
            fine_resolution=fine_resolution,
            coarse_resolution=coarse_resolution,
        )

        fine_step = self.fine_coastline_step
        for convention, out_filename in self.output_filenames.items():
            in_filename = f'fine_{fine_step.output_filenames[convention]}'
            ds_fine = xr.open_dataset(in_filename)
            ds_coarse = _coastline_remap_dataset(
                ds_fine=ds_fine,
                scale=scale,
                mask_threshold=mask_threshold,
                convention=convention,
                fine_resolution=fine_resolution,
                coarse_resolution=coarse_resolution,
                fine_step_subdir=fine_step.subdir,
            )
            _write_netcdf_with_fill_values(ds_coarse, out_filename)


def _compute_scale(fine_resolution, coarse_resolution):
    scale = coarse_resolution / fine_resolution
    scale_int = int(round(scale))
    if abs(scale - scale_int) > 1e-6:
        raise ValueError(
            f'Coarse resolution {coarse_resolution}° is not an integer '
            f'multiple of fine resolution {fine_resolution}°.'
        )
    return scale_int


def _coastline_remap_dataset(
    ds_fine,
    scale,
    mask_threshold,
    convention,
    fine_resolution,
    coarse_resolution,
    fine_step_subdir,
):
    fine_mask = ds_fine['ocean_mask'].values.astype(np.float64)
    fine_dist = ds_fine['signed_distance'].values.astype(np.float64)

    ocean_fraction = _block_average(fine_mask, scale)
    ocean_mask = (ocean_fraction >= mask_threshold).astype(np.int8)

    abs_dist = np.abs(fine_dist)
    coarse_abs_dist = _bilinear_zoom(abs_dist, scale)
    signed_distance = np.where(ocean_mask, coarse_abs_dist, -coarse_abs_dist)

    coarse_lat = _coarsen_coordinate(ds_fine['lat'].values, scale)
    coarse_lon = _coarsen_coordinate(ds_fine['lon'].values, scale)

    ds_coarse = xr.Dataset(
        coords=dict(
            lat=xr.DataArray(coarse_lat, dims=('lat',)),
            lon=xr.DataArray(coarse_lon, dims=('lon',)),
        )
    )
    dims = ('lat', 'lon')
    ds_coarse['ocean_mask'] = xr.DataArray(ocean_mask, dims=dims)
    ds_coarse['signed_distance'] = xr.DataArray(
        signed_distance.astype(np.float32), dims=dims
    )

    ds_coarse['ocean_mask'].attrs['long_name'] = (
        'Ocean mask remapped from finest resolution and thresholded'
    )
    ds_coarse['signed_distance'].attrs['long_name'] = (
        'Signed distance to the nearest coastline sample'
    )
    ds_coarse['signed_distance'].attrs['units'] = 'm'

    ds_coarse.attrs.update(
        dict(
            coastline_convention=convention,
            target_grid='lat_lon',
            target_grid_resolution_degrees=coarse_resolution,
            coastline_source='remapped_from_fine_grid',
            mask_threshold=mask_threshold,
            flood_fill_seed_strategy='inherited_from_finest_resolution',
            sign_convention='negative_over_land_positive_over_ocean',
            coastline_edge_definition=(
                'east and north cell-edge transitions on the '
                f'{fine_resolution}° source grid'
            ),
            coastline_distance_definition=(
                'bilinearly remapped unsigned distance from '
                f'{fine_resolution}° grid, re-signed by remapped ocean mask'
            ),
            source_resolution_degrees=fine_resolution,
            source_coastline_step=fine_step_subdir,
        )
    )

    return ds_coarse


def _block_average(arr, scale):
    """
    Conservatively remap a 2-D array by averaging scale×scale blocks.

    Parameters
    ----------
    arr : numpy.ndarray
        Fine-grid array with shape (n_lat_fine, n_lon_fine)

    scale : int
        Integer downscaling factor

    Returns
    -------
    numpy.ndarray
        Coarse-grid array with shape (n_lat_fine // scale, n_lon_fine // scale)
    """
    n_lat, n_lon = arr.shape
    return arr.reshape(n_lat // scale, scale, n_lon // scale, scale).mean(
        axis=(1, 3)
    )


def _bilinear_zoom(arr, scale):
    """
    Bilinearly remap a 2-D fine-grid array to the coarser grid.

    Parameters
    ----------
    arr : numpy.ndarray
        Fine-grid array with shape (n_lat_fine, n_lon_fine)

    scale : int
        Integer downscaling factor (zoom = 1/scale)

    Returns
    -------
    numpy.ndarray
        Coarse-grid array with shape (n_lat_fine // scale, n_lon_fine // scale)
    """
    return np.asarray(
        ndimage.zoom(arr, zoom=1.0 / scale, order=1, prefilter=False)
    )


def _coarsen_coordinate(coord, scale):
    """
    Compute the coarse-grid coordinate by block-averaging the fine coordinate.

    Parameters
    ----------
    coord : numpy.ndarray
        Fine-grid 1-D coordinate array of length n

    scale : int
        Integer downscaling factor

    Returns
    -------
    numpy.ndarray
        Coarse coordinate array of length n // scale
    """
    n = coord.size
    return coord.reshape(n // scale, scale).mean(axis=1)
