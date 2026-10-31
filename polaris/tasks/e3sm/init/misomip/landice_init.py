import os
import shutil

import netCDF4
import numpy as np
import xarray as xr

from polaris.remap import MappingFileStep
from polaris.step import Step
from polaris.tasks.e3sm.init.misomip.calving import calve
from polaris.tasks.e3sm.init.misomip.land_ice_fields import read_map
from polaris.tasks.e3sm.init.misomip.names import get_grid_names
from polaris.tasks.e3sm.init.misomip.projection import (
    get_lat_lon,
    get_projection_string,
)

#: The ISOMIP+ input geometry of each protocol experiment, in the ocean
#: component's ``isomip_plus`` database
INPUT_FILENAMES = {
    'ocean1': 'Ocean1_input_geom_v1.01.nc',
    'ocean2': 'Ocean2_input_geom_v1.01.nc',
    'ocean3': 'Ocean3_input_geom_v1.01.nc',
    'ocean4': 'Ocean4_input_geom_v1.01.nc',
}

#: The input geometry each experiment's MALI initial condition comes from,
#: or ``None`` for the MISMIP+ steady state
INPUT_GEOMETRY = {
    'ocean0': 'ocean1',
    'ocean1': 'ocean1',
    'ocean2': 'ocean2',
    'ocean3': 'ocean3',
    'ocean4': 'ocean4',
    'iceocean1r': None,
}

#: MALI's time at the start of the E3SM runs
START_XTIME = '00001-01-01_00:00:00'


class InputMapStep(MappingFileStep):
    """
    A step for making the conservative map from the ISOMIP+ input grid to
    MALI's mesh
    """

    def __init__(self, component, subdir, landice_mesh_step):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory for the step

        landice_mesh_step : polaris.Step
            The step that writes MALI's SCRIP file
        """
        super().__init__(
            component=component,
            name='map_input_to_landice_aave',
            subdir=subdir,
            ntasks=8,
            min_tasks=1,
            map_filename='map.nc',
            method='conserve',
        )
        # every input file has the same grid
        self.add_input_file(
            filename='input_geometry.nc',
            target=INPUT_FILENAMES['ocean1'],
            database='isomip_plus',
            database_component='ocean',
        )
        self.add_input_file(
            filename='dst_scrip.nc',
            work_dir_target=os.path.join(
                landice_mesh_step.path, 'landice_scrip.nc'
            ),
        )
        self.add_output_file(filename='map.nc')

    def runtime_setup(self):
        """
        Set the input grid from the projection and MALI's mesh from its
        SCRIP file
        """
        grids = get_grid_names(self.config)
        self.remapper.src_from_proj(
            filename='input_geometry.nc',
            mesh_name='isomip_plus_input',
            x_var='x',
            y_var='y',
            proj_str=get_projection_string(),
        )
        self.dst_from_scrip(
            filename='dst_scrip.nc', mesh_name=grids['landice']
        )
        super().runtime_setup()


class LandiceInitStep(Step):
    """
    A step for making MALI's initial condition for an experiment

    Attributes
    ----------
    experiment : str
        The experiment
    """

    def __init__(
        self, component, subdir, experiment, spin_up_step, input_map_step
    ):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory for the step

        experiment : str
            One of the experiments in :py:data:`INPUT_GEOMETRY`

        spin_up_step : polaris.Step
            The MISMIP+ step whose output is the steady state

        input_map_step : InputMapStep
            The step that makes the map from the input grid to MALI's mesh
        """
        super().__init__(
            component=component, name='landice_init', subdir=subdir
        )
        self.experiment = experiment
        self.add_input_file(
            filename='steady_state.nc',
            work_dir_target=os.path.join(spin_up_step.path, 'steady_state.nc'),
        )
        geometry = INPUT_GEOMETRY[experiment]
        if geometry is not None:
            self.add_input_file(
                filename='input_geometry.nc',
                target=INPUT_FILENAMES[geometry],
                database='isomip_plus',
                database_component='ocean',
            )
            self.add_input_file(
                filename='map.nc',
                work_dir_target=os.path.join(input_map_step.path, 'map.nc'),
            )
        self.add_output_file(filename='landice_init.nc')

    def run(self):
        """
        Run this step
        """
        filename = 'landice_init.nc'
        shutil.copyfile('steady_state.nc', filename)
        with netCDF4.Dataset(filename, 'a') as ds:
            if INPUT_GEOMETRY[self.experiment] is not None:
                x_cell = ds.variables['xCell'][:]
                bed = ds.variables['bedTopography'][0, :]
                steady_thickness = ds.variables['thickness'][0, :]
                with xr.open_dataset('input_geometry.nc') as ds_input:
                    if 't' in ds_input.dims:
                        ds_input = ds_input.isel(t=[0])
                    else:
                        ds_input = ds_input.expand_dims(dim='t')
                    thickness = get_landice_thickness(
                        ds_input=ds_input,
                        map_filename='map.nc',
                        steady_thickness=steady_thickness,
                        bed_topography=bed,
                        x_cell=x_cell,
                    )
                ds.variables['thickness'][0, :] = thickness[0, :]
                self.logger.info(
                    f'Ice volume: steady state '
                    f'{_volume(ds, steady_thickness):.6e} m^3, initial '
                    f'condition {_volume(ds, thickness[0, :]):.6e} m^3'
                )
            set_lat_lon(ds)
            set_xtime(ds, START_XTIME)


def get_landice_thickness(
    ds_input, map_filename, steady_thickness, bed_topography, x_cell
):
    """
    Get MALI's thickness from records of the ISOMIP+ input geometry: the
    input remapped to MALI's cells where the input covers them, the steady
    state upstream, all calved

    Parameters
    ----------
    ds_input : xarray.Dataset
        The input geometry, with dimensions ``t``, ``y`` and ``x``

    map_filename : str
        The conservative map from the input grid to MALI's mesh

    steady_thickness : numpy.ndarray
        The thickness of the steady state on MALI's cells

    bed_topography : numpy.ndarray
        The bed elevation on MALI's cells

    x_cell : numpy.ndarray
        The x coordinate of MALI's cells

    Returns
    -------
    thickness : numpy.ndarray
        The thickness on MALI's cells, for each record
    """
    remapped = remap_input_thickness(ds_input, map_filename)
    x_min = _get_input_x_min(ds_input)
    thickness = np.where(x_cell >= x_min, remapped, steady_thickness)
    return calve(thickness, bed_topography, x_cell)


def remap_input_thickness(ds_input, map_filename):
    """
    Remap the thickness of records of the ISOMIP+ input geometry to MALI's
    cells, as the mean over the part of each cell the input covers

    Parameters
    ----------
    ds_input : xarray.Dataset
        The input geometry, with dimensions ``t``, ``y`` and ``x``

    map_filename : str
        The conservative map from the input grid to MALI's mesh

    Returns
    -------
    thickness : numpy.ndarray
        The thickness on MALI's cells, for each record, and zero where the
        input covers no part of a cell
    """
    thickness = ds_input.upperSurface - ds_input.lowerSurface
    thickness = thickness.transpose('t', 'y', 'x').values
    # the map's cells are in the order of the input's (y, x)
    thickness = thickness.reshape(thickness.shape[0], -1)
    matrix = read_map(map_filename)
    covered = np.asarray(matrix.sum(axis=1)).ravel()
    remapped = np.asarray(matrix @ thickness.T).T
    return np.where(covered > 0.0, remapped / np.maximum(covered, 1e-30), 0.0)


def set_lat_lon(ds):
    """
    Set the projection's latitude and longitude in a MALI file

    Parameters
    ----------
    ds : netCDF4.Dataset
        The file, open for appending
    """
    for loc in ['Cell', 'Edge', 'Vertex']:
        lat, lon = get_lat_lon(
            ds.variables[f'x{loc}'][:], ds.variables[f'y{loc}'][:]
        )
        ds.variables[f'lat{loc}'][:] = lat
        ds.variables[f'lon{loc}'][:] = lon


def set_xtime(ds, xtime_value):
    """
    Set the time of the first record of a MALI file

    Parameters
    ----------
    ds : netCDF4.Dataset
        The file, open for appending

    xtime_value : str
        The time, padded with null characters as MALI writes it
    """
    xtime = ds.variables['xtime']
    xtime.set_auto_chartostring(False)
    value = xtime_value.encode()
    xtime[0, :] = np.frombuffer(
        value.ljust(xtime.shape[-1], b'\0'), dtype='S1'
    )


def _get_input_x_min(ds_input):
    """
    The x coordinate of the edge of the input grid's first column
    """
    x = ds_input.x.values
    return x[0] - 0.5 * (x[1] - x[0])


def _volume(ds, thickness):
    """
    The ice volume, from MALI's planar cell areas
    """
    return float(np.sum(thickness * ds.variables['areaCell'][:]))
