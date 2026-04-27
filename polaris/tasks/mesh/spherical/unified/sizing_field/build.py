import os

import numpy as np
import xarray as xr

from polaris.mesh.spherical.unified import get_unified_mesh_family
from polaris.step import Step


class BuildSizingFieldStep(Step):
    """
    Build a unified sizing field on a shared lat-lon target grid.
    """

    def __init__(self, component, coastline_step, river_step, subdir):
        super().__init__(
            component=component,
            name='sizing_field',
            subdir=subdir,
            cpus_per_task=1,
            min_cpus_per_task=1,
        )
        self.coastline_step = coastline_step
        self.river_step = river_step
        self.sizing_field_filename = 'sizing_field.nc'

    def setup(self):
        """
        Link coastline and river products and declare outputs.
        """
        convention = self.config.get('unified_mesh', 'coastline_convention')
        self.add_input_file(
            filename='coastline.nc',
            work_dir_target=os.path.join(
                self.coastline_step.path,
                self.coastline_step.output_filenames[convention],
            ),
        )
        self.add_input_file(
            filename='river_network.nc',
            work_dir_target=os.path.join(
                self.river_step.path, self.river_step.masks_filename
            ),
        )
        self._get_mesh_family().setup_sizing_field_step(self)
        self.add_output_file(filename=self.sizing_field_filename)

    def run(self):
        """
        Build the sizing-field dataset and write it to NetCDF.
        """
        section = self.config['sizing_field']
        unified_section = self.config['unified_mesh']

        with xr.open_dataset('coastline.nc') as ds_coastline:
            with xr.open_dataset('river_network.nc') as ds_river:
                ocean_background = self._get_ocean_background(
                    ds_coastline=ds_coastline, section=section
                )
                ds_sizing = sizing_field_dataset(
                    ds_coastline=ds_coastline,
                    ds_river=ds_river,
                    resolution=unified_section.getfloat('resolution_latlon'),
                    mesh_name=unified_section.get('mesh_name'),
                    ocean_background=ocean_background,
                    land_background_km=section.getfloat('land_background_km'),
                    enable_coastline_refinement=section.getboolean(
                        'enable_coastline_refinement'
                    ),
                    coastline_transition_land_km=section.getfloat(
                        'coastline_transition_land_km'
                    ),
                    enable_river_channel_refinement=section.getboolean(
                        'enable_river_channel_refinement'
                    ),
                    river_channel_km=section.getfloat('river_channel_km'),
                    enable_river_outlet_refinement=section.getboolean(
                        'enable_river_outlet_refinement'
                    ),
                    river_outlet_km=section.getfloat('river_outlet_km'),
                )

        ds_sizing.attrs['source_coastline_step'] = self.coastline_step.subdir
        ds_sizing.attrs['source_river_step'] = self.river_step.subdir
        ds_sizing.to_netcdf(self.sizing_field_filename)

    def _get_ocean_background(self, ds_coastline, section):
        """
        Build the ocean background field for the shared target grid.
        """
        return self._get_mesh_family().build_ocean_background(
            ds_coastline=ds_coastline, section=section
        )

    def _get_mesh_family(self):
        """
        Get the unified-mesh family object for this step's shared config.
        """
        return get_unified_mesh_family(self.config)


def sizing_field_dataset(
    ds_coastline,
    ds_river,
    resolution,
    mesh_name,
    ocean_background,
    land_background_km=240.0,
    enable_coastline_refinement=True,
    coastline_transition_land_km=0.0,
    enable_river_channel_refinement=True,
    river_channel_km=240.0,
    enable_river_outlet_refinement=True,
    river_outlet_km=240.0,
):
    """
    Build the unified sizing-field dataset from coastline and river products.
    """
    _validate_shared_grid(ds_coastline=ds_coastline, ds_river=ds_river)

    lat = ds_coastline.lat.values
    lon = ds_coastline.lon.values
    dims = ('lat', 'lon')
    ocean_background = np.asarray(ocean_background, dtype=float)
    expected_shape = (lat.size, lon.size)
    if ocean_background.shape != expected_shape:
        raise ValueError(
            'Ocean background must have shape '
            f'{expected_shape}, got {ocean_background.shape}.'
        )

    ocean_mask = ds_coastline.ocean_mask.values.astype(bool)
    signed_distance = ds_coastline.signed_distance.values.astype(float)
    river_channel_mask = ds_river.river_channel_mask.values.astype(bool)
    river_outlet_mask = ds_river.river_outlet_mask.values.astype(bool)
    land_background = np.full(ocean_background.shape, land_background_km)
    background = np.where(ocean_mask, ocean_background, land_background)

    river_channel_candidate = _build_mask_candidate(
        background=land_background,
        mask=river_channel_mask,
        enabled=enable_river_channel_refinement,
        target_km=river_channel_km,
    )
    river_outlet_candidate = _build_mask_candidate(
        background=land_background,
        mask=river_outlet_mask,
        enabled=enable_river_outlet_refinement,
        target_km=river_outlet_km,
    )

    land_river_stack = np.stack(
        [
            land_background,
            river_channel_candidate,
            river_outlet_candidate,
        ],
        axis=0,
    )
    land_river_control = np.argmin(land_river_stack, axis=0).astype(np.int8)
    land_river_cell_width = np.take_along_axis(
        land_river_stack, land_river_control[np.newaxis, ...], axis=0
    )[0]
    land_river_control = np.array([0, 2, 3], dtype=np.int8)[land_river_control]

    composed_background = np.where(
        ocean_mask, ocean_background, land_river_cell_width
    )
    coastline_candidate = _build_coastline_candidate(
        background=composed_background,
        ocean_background=ocean_background,
        ocean_mask=ocean_mask,
        signed_distance=signed_distance,
        enabled=enable_coastline_refinement,
        land_transition_km=coastline_transition_land_km,
    )
    final_cell_width = coastline_candidate

    active_control = np.where(ocean_mask, 0, land_river_control)
    active_control = active_control.astype(np.int8)
    coastline_active = ~np.isclose(coastline_candidate, composed_background)
    active_control[coastline_active] = 1
    coastal_transition_delta = final_cell_width - composed_background

    ds_sizing = xr.Dataset(
        coords=dict(lat=ds_coastline.lat, lon=ds_coastline.lon)
    )
    data_vars = {
        'cellWidth': final_cell_width.astype(np.float32),
        'background_cell_width': background.astype(np.float32),
        'ocean_background_cell_width': ocean_background.astype(np.float32),
        'land_river_cell_width': land_river_cell_width.astype(np.float32),
        'pre_coastline_cell_width': composed_background.astype(np.float32),
        'coastline_cell_width': coastline_candidate.astype(np.float32),
        'coastal_transition_delta': coastal_transition_delta.astype(
            np.float32
        ),
        'river_channel_cell_width': river_channel_candidate.astype(np.float32),
        'river_outlet_cell_width': river_outlet_candidate.astype(np.float32),
        'active_control': active_control,
    }
    for var_name, values in data_vars.items():
        ds_sizing[var_name] = xr.DataArray(values, dims=dims)

    ds_sizing.attrs.update(
        dict(
            mesh_name=mesh_name,
            target_grid='lat_lon',
            target_grid_resolution_degrees=resolution,
            active_control_meanings=(
                '0=background 1=coastline 2=river_channel 3=river_outlet'
            ),
        )
    )
    _add_mask_candidate_attrs(
        ds_sizing=ds_sizing,
        prefix='river_channel',
        mask=river_channel_mask,
        candidate=river_channel_candidate,
        background=land_background,
    )
    _add_mask_candidate_attrs(
        ds_sizing=ds_sizing,
        prefix='river_outlet',
        mask=river_outlet_mask,
        candidate=river_outlet_candidate,
        background=land_background,
    )
    ds_sizing.cellWidth.attrs['units'] = 'km'
    ds_sizing.background_cell_width.attrs['units'] = 'km'
    ds_sizing.ocean_background_cell_width.attrs['units'] = 'km'
    ds_sizing.land_river_cell_width.attrs['units'] = 'km'
    ds_sizing.pre_coastline_cell_width.attrs['units'] = 'km'
    ds_sizing.coastline_cell_width.attrs['units'] = 'km'
    ds_sizing.coastal_transition_delta.attrs['units'] = 'km'
    ds_sizing.river_channel_cell_width.attrs['units'] = 'km'
    ds_sizing.river_outlet_cell_width.attrs['units'] = 'km'
    ds_sizing.active_control.attrs['long_name'] = (
        'Index of the active sizing control'
    )

    return ds_sizing


def _validate_shared_grid(ds_coastline, ds_river):
    """
    Validate that coastline and river products share the same target grid.
    """
    for coord_name in ['lat', 'lon']:
        if (
            coord_name not in ds_coastline.coords
            or coord_name not in ds_river.coords
        ):
            raise ValueError(f'Missing required coordinate {coord_name!r}.')

        if not np.array_equal(
            ds_coastline[coord_name].values, ds_river[coord_name].values
        ):
            raise ValueError(
                'Coastline and river products must share the same lat-lon '
                f'grid. Mismatch found in coordinate {coord_name!r}.'
            )


def _add_mask_candidate_attrs(ds_sizing, prefix, mask, candidate, background):
    """
    Add provenance counts for a mask-based sizing candidate.
    """
    ds_sizing.attrs[f'{prefix}_mask_count'] = int(np.count_nonzero(mask))
    ds_sizing.attrs[f'{prefix}_finer_than_background_count'] = int(
        np.count_nonzero(mask & (candidate < background))
    )
    ds_sizing.attrs[f'{prefix}_equal_to_background_count'] = int(
        np.count_nonzero(mask & np.isclose(candidate, background))
    )
    ds_sizing.attrs[f'{prefix}_coarser_than_background_count'] = int(
        np.count_nonzero(mask & (candidate > background))
    )


def _build_mask_candidate(background, mask, enabled, target_km):
    """
    Build a mask-based candidate field in km.
    """
    if not enabled:
        return background.copy()

    return np.where(mask, target_km, background).astype(float)


def _build_coastline_candidate(
    background,
    ocean_background,
    ocean_mask,
    signed_distance,
    enabled,
    land_transition_km,
):
    """
    Build the coastline candidate field in km.
    """
    candidate = background.copy()
    if not enabled:
        return candidate

    land_transition_m = land_transition_km * 1.0e3
    land_side = np.logical_not(ocean_mask) & (signed_distance <= 0.0)

    _apply_transition(
        candidate=candidate,
        target=ocean_background.astype(float),
        background=background,
        signed_distance=np.abs(signed_distance),
        mask=land_side,
        transition_m=land_transition_m,
    )
    return candidate


def _apply_transition(
    candidate, target, background, signed_distance, mask, transition_m
):
    """
    Apply a linear transition from the coastline target back to background.
    """
    if transition_m < 0.0:
        raise ValueError('Transition widths must be nonnegative.')

    if transition_m == 0.0:
        zero_mask = mask & np.isclose(signed_distance, 0.0)
        candidate[zero_mask] = target[zero_mask]
        return

    transition_mask = mask & (signed_distance <= transition_m)
    fraction = signed_distance[transition_mask] / transition_m
    candidate[transition_mask] = target[transition_mask] + fraction * (
        background[transition_mask] - target[transition_mask]
    )
