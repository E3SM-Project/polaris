import os

import xarray as xr

from polaris.ocean.model import OceanIOStep

from .remap_jra55 import JRA55_ON_MESH_FILENAME


class ForcingStep(OceanIOStep):
    """
    A step that reads the remapped JRA55-do wind stress and writes the
    model-specific surface forcing file.

    Both models take zonal and meridional stress components at cell centres
    and project onto edges themselves, so no vector rotation happens here.
    The field is authored in MPAS-Ocean names and renamed on write by
    :py:meth:`polaris.ocean.model.OceanIOStep.write_forcing_dataset`, which
    also adds the ``Time`` dimension MPAS-Ocean's Registry requires and Omega
    forbids.

    Only wind stress is written.  Surface restoring, thermal and freshwater
    fluxes, and time-varying forcing are future work.

    Attributes
    ----------
    remap_jra55_step : polaris.Step
        The upstream step that produces ``jra55_on_mesh.nc``.
    """

    def __init__(self, component, subdir, remap_jra55_step):
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
        """
        super().__init__(
            component=component,
            name='forcing',
            subdir=subdir,
            ntasks=1,
            min_tasks=1,
        )
        self.remap_jra55_step = remap_jra55_step

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
        self.add_output_file(filename=self.get_forcing_filename())

    def run(self):
        """
        Write the model-specific ``forcing.nc``.
        """
        config = self.config
        with xr.open_dataset(JRA55_ON_MESH_FILENAME) as ds_stress:
            ds = xr.Dataset()
            ds['windStressZonal'] = ds_stress.taux
            ds['windStressMeridional'] = ds_stress.tauy

        ds.windStressZonal.attrs = {
            'units': 'N m-2',
            'long_name': 'Zonal (eastward) component of wind stress',
        }
        ds.windStressMeridional.attrs = {
            'units': 'N m-2',
            'long_name': 'Meridional (northward) component of wind stress',
        }

        self.write_forcing_dataset(ds, self.get_forcing_filename(), config)
