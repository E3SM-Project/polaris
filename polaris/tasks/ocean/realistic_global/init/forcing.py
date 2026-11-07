import os

import xarray as xr

from polaris.ocean.model import OceanIOStep

from .remap_jra55 import JRA55_ON_MESH_FILENAME


class ForcingStep(OceanIOStep):
    """
    A step that reads the remapped JRA55-do wind stress and writes the
    model-specific surface forcing file.

    Both models take zonal and meridional stress components at cell centers
    and project onto edges themselves, so no vector rotation happens here.
    The field is authored in MPAS-Ocean names and renamed on write by
    :py:meth:`polaris.ocean.model.OceanIOStep.write_forcing_dataset`, which
    also adds the ``Time`` dimension MPAS-Ocean's Registry requires and Omega
    forbids.

    Only wind stress is written.  Surface restoring, thermal and freshwater
    fluxes, and time-varying forcing are future work.  There is no wind stress
    under Antarctic land ice.

    Attributes
    ----------
    remap_jra55_step : polaris.Step
        The upstream step that produces ``jra55_on_mesh.nc``.

    cull_topo_step : polaris.Step
        The upstream step that produces ``topography_culled.nc``, with the
        land-ice mask on the culled mesh.
    """

    def __init__(self, component, subdir, remap_jra55_step, cull_topo_step):
        """
        Create the step.

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the step belongs to.

        subdir : str
            The subdirectory for the step.

        remap_jra55_step : polaris.Step
            The step that produces ``jra55_on_mesh.nc``.

        cull_topo_step : polaris.Step
            The step that produces ``topography_culled.nc``.
        """
        super().__init__(
            component=component,
            name='forcing',
            subdir=subdir,
            ntasks=1,
            min_tasks=1,
        )
        self.remap_jra55_step = remap_jra55_step
        self.cull_topo_step = cull_topo_step

    def setup(self):
        """
        Declare the input and output files.
        """
        super().setup()
        self.add_input_file(
            filename=JRA55_ON_MESH_FILENAME,
            work_dir_target=os.path.join(
                self.remap_jra55_step.path,
                JRA55_ON_MESH_FILENAME,
            ),
        )
        self.add_input_file(
            filename='topography_culled.nc',
            work_dir_target=os.path.join(
                self.cull_topo_step.path, 'topography_culled.nc'
            ),
        )
        self.add_output_file(filename=self.get_forcing_filename())
        self.add_cf_check(self.get_forcing_filename())

    def run(self):
        """
        Write the model-specific ``forcing.nc``.
        """
        config = self.config
        with xr.open_dataset(JRA55_ON_MESH_FILENAME) as ds_stress:
            ds = xr.Dataset()
            # the remapped lat and lon are not forcing fields, so they are
            # left behind
            ds['windStressZonal'] = ('nCells', ds_stress.taux.values)
            ds['windStressMeridional'] = ('nCells', ds_stress.tauy.values)

        with xr.open_dataset('topography_culled.nc') as ds_topo:
            land_ice_mask = ds_topo.landIceMask.values
        ds = mask_wind_stress_under_land_ice(ds, land_ice_mask)

        ds.windStressZonal.attrs = {
            'units': 'N m-2',
            'long_name': 'Zonal (eastward) component of wind stress',
        }
        ds.windStressMeridional.attrs = {
            'units': 'N m-2',
            'long_name': 'Meridional (northward) component of wind stress',
        }

        self.write_forcing_dataset(ds, self.get_forcing_filename(), config)


def mask_wind_stress_under_land_ice(ds, land_ice_mask):
    """
    Set the wind stress to zero under Antarctic land ice.

    Parameters
    ----------
    ds : xarray.Dataset
        A dataset with ``windStressZonal`` and ``windStressMeridional`` at
        cell centers

    land_ice_mask : numpy.ndarray
        1 in cells under land ice and 0 elsewhere

    Returns
    -------
    ds : xarray.Dataset
        The dataset with the wind stress zeroed under land ice
    """
    under_ice = xr.DataArray(land_ice_mask == 1, dims=('nCells',))
    for name in ['windStressZonal', 'windStressMeridional']:
        attrs = ds[name].attrs
        ds[name] = ds[name].where(~under_ice, 0.0)
        ds[name].attrs = attrs
    return ds
