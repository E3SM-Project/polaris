import os

import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf

from polaris import Step
from polaris.tasks.ocean.realistic_global.forcing.jra55.stress import (
    JRA55_STRESS_FILENAME,
)

JRA55_ON_MESH_FILENAME = 'jra55_on_mesh.nc'

CARTESIAN_VAR_NAMES = ['tau_cart_x', 'tau_cart_y', 'tau_cart_z']


class RemapJra55Step(Step):
    """
    A step for applying the JRA55-do mapping weights built by
    :py:class:`.Jra55MapStep`, remapping the wind-stress product from the
    native TL319 grid to MPAS cell centers.

    The stress is a vector, and the local east/north basis its components
    are given in rotates with position, most quickly near the poles.  The
    step therefore remaps the three Cartesian components of the stress as
    scalars and rotates them back to east/north at each cell center, rather
    than remapping the zonal and meridional components independently.  This
    makes the result independent of how the mapping tool treats the pole.

    Every cell of the culled mesh has to be covered by the weights.
    ``ncremap`` writes zero rather than a missing value to a cell the weights
    do not reach, so the step checks the coverage recorded in the mapping
    file and fails rather than let a gap reach the forcing file as zero
    stress.

    Attributes
    ----------
    stress_step : polaris.Step
        The upstream step that produces the JRA55-do wind-stress product.

    jra55_map_step : polaris.Step
        The upstream step that builds the JRA55-to-mesh mapping file.

    cull_mesh_step : polaris.tasks.e3sm.init.topo.cull.cull.CullMeshStep
        The upstream step that produces the culled MPAS mesh, whose cell
        centers the stress is rotated to.
    """

    def __init__(
        self, component, subdir, stress_step, jra55_map_step, cull_mesh_step
    ):
        """
        Create the step.

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the step belongs to.

        subdir : str
            The subdirectory for the step.

        stress_step : polaris.Step
            The step that produces the JRA55-do wind-stress product.

        jra55_map_step : polaris.Step
            The step that builds the JRA55-to-mesh mapping file.

        cull_mesh_step : polaris.tasks.e3sm.init.topo.cull.cull.CullMeshStep
            The step that produces the culled ocean mesh files.
        """
        super().__init__(
            component=component,
            name='remap_jra55',
            subdir=subdir,
            ntasks=1,
            min_tasks=1,
        )
        self.stress_step = stress_step
        self.jra55_map_step = jra55_map_step
        self.cull_mesh_step = cull_mesh_step
        self.add_dependency(jra55_map_step, name='jra55_map')
        self.add_output_file(JRA55_ON_MESH_FILENAME)

    def setup(self):
        """
        Declare the JRA55-do and culled-mesh input files.
        """
        super().setup()
        self.add_input_file(
            filename=JRA55_STRESS_FILENAME,
            work_dir_target=os.path.join(
                self.stress_step.path,
                JRA55_STRESS_FILENAME,
            ),
        )
        self.add_input_file(
            filename='mesh.nc',
            work_dir_target=os.path.join(
                self.cull_mesh_step.path,
                'culled_ocean_mesh.nc',
            ),
        )

    def run(self):
        """
        Remap the wind stress to MPAS cell centers in Cartesian components,
        rotate it back to zonal and meridional components, check that no cell
        is missing, and write ``jra55_on_mesh.nc``.
        """
        logger = self.logger
        # the remapper (including the path to the mapping file it built)
        # comes from the map step, which has already run
        remapper = self.dependencies['jra55_map'].remapper

        with xr.open_dataset(JRA55_STRESS_FILENAME) as ds_stress:
            ds_stress = ds_stress.load()
        write_netcdf(
            stress_to_cartesian(ds_stress), 'jra55_stress_cartesian.nc'
        )

        remapper.ncremap(
            in_filename='jra55_stress_cartesian.nc',
            out_filename='jra55_on_mesh_raw.nc',
            variable_list=CARTESIAN_VAR_NAMES,
            logger=logger,
        )

        with xr.open_dataset(remapper.map_filename) as ds_map:
            frac_b = ds_map.frac_b.values

        with xr.open_dataset('mesh.nc') as ds_mesh:
            lon_cell = ds_mesh.lonCell.values
            lat_cell = ds_mesh.latCell.values

        with xr.open_dataset('jra55_on_mesh_raw.nc') as ds_raw:
            ds_raw = self._postprocess_remapped_output(ds_raw).load()
        ds_out = cartesian_to_stress(
            ds_raw, lon_cell=lon_cell, lat_cell=lat_cell
        )
        for var in ['taux', 'tauy']:
            ds_out[var].attrs = ds_stress[var].attrs

        check_no_missing_cells(
            ds=ds_out, var_names=['taux', 'tauy'], frac_b=frac_b
        )

        write_netcdf(ds_out, JRA55_ON_MESH_FILENAME)

    @staticmethod
    def _postprocess_remapped_output(ds):
        """
        Clean up the raw ncremap output: rename ``ncol`` to ``nCells`` and
        retain only the Cartesian stress components.

        Parameters
        ----------
        ds : xarray.Dataset
            Raw dataset produced by ncremap, with the horizontal dimension
            named ``ncol``.

        Returns
        -------
        xarray.Dataset
            Dataset with dimension ``nCells`` and the Cartesian stress
            components.
        """
        if 'ncol' in ds.dims:
            ds = ds.rename({'ncol': 'nCells'})

        return ds[CARTESIAN_VAR_NAMES]


def stress_to_cartesian(ds):
    """
    Convert zonal and meridional wind stress on a latitude-longitude grid to
    Cartesian components.

    Parameters
    ----------
    ds : xarray.Dataset
        A dataset with ``taux`` and ``tauy`` on ``(lat, lon)`` and the
        coordinates ``lat`` and ``lon`` in degrees

    Returns
    -------
    xarray.Dataset
        ``ds`` with ``taux`` and ``tauy`` replaced by the Cartesian components
        named in ``CARTESIAN_VAR_NAMES``, keeping the coordinates (and any
        bounds) that ``ncremap`` needs to recognize the grid
    """
    lon = np.deg2rad(ds.lon)
    lat = np.deg2rad(ds.lat)
    taux = ds.taux
    tauy = ds.tauy
    components = [
        -np.sin(lon) * taux - np.sin(lat) * np.cos(lon) * tauy,
        np.cos(lon) * taux - np.sin(lat) * np.sin(lon) * tauy,
        np.cos(lat) * tauy,
    ]
    ds_out = ds.drop_vars(['taux', 'tauy'])
    for var, component, axis in zip(
        CARTESIAN_VAR_NAMES, components, 'xyz', strict=True
    ):
        ds_out[var] = component.transpose(*taux.dims)
        ds_out[var].attrs = {
            'units': taux.attrs.get('units', 'N m-2'),
            'long_name': f'surface wind stress, Cartesian {axis} component',
        }
    return ds_out


def cartesian_to_stress(ds, lon_cell, lat_cell):
    """
    Rotate Cartesian wind stress at MPAS cell centers back to zonal and
    meridional components.

    The radial part of the remapped vector, which bilinear interpolation
    between points on a sphere leaves slightly nonzero, is discarded.

    Parameters
    ----------
    ds : xarray.Dataset
        A dataset with the components named in ``CARTESIAN_VAR_NAMES`` on
        ``nCells``

    lon_cell, lat_cell : numpy.ndarray
        The longitude and latitude of the cell centers in radians

    Returns
    -------
    xarray.Dataset
        A dataset with ``taux`` and ``tauy`` on ``nCells``
    """
    tau_x, tau_y, tau_z = (ds[var] for var in CARTESIAN_VAR_NAMES)
    sin_lon = xr.DataArray(np.sin(lon_cell), dims='nCells')
    cos_lon = xr.DataArray(np.cos(lon_cell), dims='nCells')
    sin_lat = xr.DataArray(np.sin(lat_cell), dims='nCells')
    cos_lat = xr.DataArray(np.cos(lat_cell), dims='nCells')
    ds_out = xr.Dataset()
    ds_out['taux'] = -sin_lon * tau_x + cos_lon * tau_y
    ds_out['tauy'] = (
        -sin_lat * (cos_lon * tau_x + sin_lon * tau_y) + cos_lat * tau_z
    )
    return ds_out


def check_no_missing_cells(ds, var_names, frac_b, tolerance=1.0e-6):
    """
    Raise an error if any cell is missing from the remapped wind stress.

    A cell is missing if the mapping weights do not fully cover it or if any
    of ``var_names`` is not finite there.  The coverage has to come from the
    mapping file: ``ncremap`` writes zero, not a missing value, to a cell
    the weights do not reach when the source has no ``_FillValue``.

    Parameters
    ----------
    ds : xarray.Dataset
        The remapped dataset, with the given variables on an ``nCells``
        dimension

    var_names : list of str
        The variables to check

    frac_b : numpy.ndarray
        The fraction of each destination cell covered by the source grid,
        from the mapping file

    tolerance : float, optional
        How far below one the coverage of a cell may be before the cell
        counts as missing
    """
    missing = frac_b < 1.0 - tolerance
    for var in var_names:
        missing |= ~np.isfinite(ds[var].values)

    n_missing = int(np.count_nonzero(missing))
    if n_missing > 0:
        raise ValueError(
            f'{n_missing} of {missing.size} cells have no remapped wind '
            f'stress.  Bilinear remapping of the JRA55-do product is '
            f'expected to cover every cell of the culled mesh.'
        )
