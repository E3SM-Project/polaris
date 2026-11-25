import os

import numpy as np
import xarray as xr

from polaris.cf import drop_dangling_references
from polaris.ocean.model import OceanIOStep

from .shortwave_extinction_map import SHORTWAVE_EXTINCTION_FILENAME

# the file Omega's ShortwaveExtinctionIn stream reads by default
SHORTWAVE_EXTINCTION_COEFFS_FILENAME = 'shortwave_extinction_coeffs.nc'

# the least coverage of a cell by the source grid for its coefficients to be
# used
MIN_COVERAGE = 0.9

EXTINCTION_VAR_NAMES = ['ExtinctionCoeffRed', 'ExtinctionCoeffBlue']

# Omega's names for the coefficients
OMEGA_VAR_NAMES = {
    'ExtinctionCoeffRed': 'ExtinctionCoeffRedCell',
    'ExtinctionCoeffBlue': 'ExtinctionCoeffBlueCell',
}


class RemapShortwaveExtinctionStep(OceanIOStep):
    """
    A step for applying the mapping weights built by
    :py:class:`.ShortwaveExtinctionMapStep`, remapping the red- and blue-band
    shortwave extinction coefficients to MPAS cell centers.

    The product has a value at every point, including land. The remapped
    coefficients are normalized by their coverage, which is slightly off one
    in a few cells.  The step fails if any cell is covered by less than
    ``MIN_COVERAGE`` or has a coefficient that is not finite and positive.

    The output is Omega's ``ShortwaveExtinctionIn`` file,
    ``shortwave_extinction_coeffs.nc``, with Omega's variable names
    ``ExtinctionCoeffRedCell`` and ``ExtinctionCoeffBlueCell`` on ``NCells``.
    It is not part of the initial state: Omega reads it on startup, including
    on restarts, from its own stream.

    Attributes
    ----------
    extinction_map_step : polaris.Step
        The upstream step that downloads the product and builds the mapping
        file.
    """

    def __init__(self, component, subdir, extinction_map_step):
        """
        Create the step.

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the step belongs to.

        subdir : str
            The subdirectory for the step.

        extinction_map_step : polaris.Step
            The step that downloads the product and builds the mapping file.
        """
        super().__init__(
            component=component,
            name='remap_shortwave_extinction',
            subdir=subdir,
            ntasks=1,
            min_tasks=1,
        )
        self.extinction_map_step = extinction_map_step
        self.add_dependency(extinction_map_step, name='extinction_map')
        self.add_output_file(SHORTWAVE_EXTINCTION_COEFFS_FILENAME)
        self.add_cf_check(SHORTWAVE_EXTINCTION_COEFFS_FILENAME)

    def setup(self):
        """
        Declare the shortwave extinction input file.
        """
        super().setup()
        self.add_input_file(
            filename=SHORTWAVE_EXTINCTION_FILENAME,
            work_dir_target=os.path.join(
                self.extinction_map_step.path,
                SHORTWAVE_EXTINCTION_FILENAME,
            ),
        )

    def run(self):
        """
        Remap and normalize the extinction coefficients on MPAS cells.
        """
        # the remapper (including the path to the mapping file it built)
        # comes from the map step, which has already run
        remapper = self.dependencies['extinction_map'].remapper

        remapper.ncremap(
            in_filename=SHORTWAVE_EXTINCTION_FILENAME,
            out_filename='shortwave_extinction_on_mesh_raw.nc',
            variable_list=EXTINCTION_VAR_NAMES,
            overwrite=True,
            logger=self.logger,
        )

        with xr.open_dataset(remapper.map_filename) as ds_map:
            frac_b = ds_map.frac_b.values

        with xr.open_dataset(SHORTWAVE_EXTINCTION_FILENAME) as ds_src:
            attrs = {var: ds_src[var].attrs for var in EXTINCTION_VAR_NAMES}

        with xr.open_dataset('shortwave_extinction_on_mesh_raw.nc') as ds_raw:
            ds_out = self._postprocess_remapped_output(ds_raw).load()
        for var in EXTINCTION_VAR_NAMES:
            ds_out[var].attrs = attrs[var]

        ds_out = _normalize_coefficients(ds_out, frac_b)

        ds_out = drop_dangling_references(ds_out).rename(OMEGA_VAR_NAMES)
        self.write_model_dataset(
            ds_out, SHORTWAVE_EXTINCTION_COEFFS_FILENAME, self.config
        )

    @staticmethod
    def _postprocess_remapped_output(ds):
        """
        Clean up the raw ncremap output: rename ``ncol`` to ``nCells`` and
        retain only the extinction coefficients.

        Parameters
        ----------
        ds : xarray.Dataset
            Raw dataset produced by ncremap, with the horizontal dimension
            named ``ncol``.

        Returns
        -------
        xarray.Dataset
            Dataset with dimension ``nCells`` and the extinction
            coefficients.
        """
        if 'ncol' in ds.dims:
            ds = ds.rename({'ncol': 'nCells'})

        return ds[EXTINCTION_VAR_NAMES].drop_vars(
            ['lat', 'lon'], errors='ignore'
        )


def _normalize_coefficients(ds, frac_b):
    """
    Normalize the remapped coefficients by coverage, failing if any cell is
    poorly covered or has a coefficient that is not finite and positive.
    """
    bad = ~np.isfinite(frac_b) | (frac_b < MIN_COVERAGE)
    safe_frac_b = np.where(bad, 1.0, frac_b)
    for var in EXTINCTION_VAR_NAMES:
        ds[var].values[:] = ds[var].values / safe_frac_b
        bad |= ~(np.isfinite(ds[var].values) & (ds[var].values > 0))

    n_bad = int(np.count_nonzero(bad))
    if n_bad > 0:
        raise ValueError(
            f'{n_bad} of {bad.size} cells have no valid shortwave '
            f'extinction coefficients.  The mapping file is probably wrong.'
        )
    return ds
