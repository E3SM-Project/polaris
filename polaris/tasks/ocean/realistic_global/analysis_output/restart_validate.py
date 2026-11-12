import os
from typing import List

import numpy as np
import xarray as xr

from polaris.ocean.model import OceanIOStep
from polaris.validate import compare_variables

#: The state variables compared between the history of the full run and the
#: restart run, which tells a model restart that is not exact from analysis
#: output that is not
STATE_VARIABLES = [
    'temperature',
    'salinity',
    'layerThickness',
    'normalVelocity',
]


class AnalysisRestartValidate(OceanIOStep):
    """
    Check that a run continued from a restart midway through an averaging
    period writes the same time means as the same run done in one go

    Every variable in every time-mean file has to match bit for bit,
    including the time and the time bounds.  The state at the end of the
    history is compared as well, so that a model restart that is not exact
    can be told from analysis output that is not.

    Attributes
    ----------
    full_run_subdir : str
        Subdirectory of the step that ran the whole period in one go

    restart_subdir : str
        Subdirectory of the run continued from a restart

    analysis_filenames : list of str
        The time-mean files to compare
    """

    def __init__(
        self,
        component,
        full_run_subdir: str,
        restart_subdir: str,
        analysis_filenames: List[str],
        indir: str,
    ):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        full_run_subdir : str
            Subdirectory of the step that ran the whole period in one go

        restart_subdir : str
            Subdirectory of the run continued from a restart

        analysis_filenames : list of str
            The time-mean files to compare, relative to each step's work
            directory

        indir : str
            the directory the step is in, to which ``name`` will be appended
        """
        super().__init__(component=component, name='validate', indir=indir)

        self.full_run_subdir = full_run_subdir
        self.restart_subdir = restart_subdir
        self.analysis_filenames = analysis_filenames

        for subdir in [full_run_subdir, restart_subdir]:
            for filename in ['output.nc'] + analysis_filenames:
                self.add_input_file(
                    filename=f'{subdir}_{filename}',
                    target=f'../{subdir}/{filename}',
                )

    def run(self):
        """
        Compare the time means and the history of the restart run with
        those of the uninterrupted run
        """
        super().run()
        logger = self.logger

        all_pass = True
        for filename in self.analysis_filenames:
            full_run = f'{self.full_run_subdir}_{filename}'
            restart = f'{self.restart_subdir}_{filename}'
            with (
                xr.open_dataset(
                    full_run, decode_times=False, mask_and_scale=False
                ) as ds1,
                xr.open_dataset(
                    restart, decode_times=False, mask_and_scale=False
                ) as ds2,
            ):
                mismatches = compare_datasets_exactly(ds1, ds2)
            if mismatches:
                all_pass = False
                logger.error(f'  {filename} FAIL')
                for mismatch in mismatches:
                    logger.error(f'    {mismatch}')
            else:
                logger.info(f'  {filename} PASS')

        full_run = f'{self.full_run_subdir}_output.nc'
        restart = f'{self.restart_subdir}_output.nc'
        for filename in [full_run, restart]:
            if not os.path.exists(filename):
                raise OSError(f'File {filename} does not exist.')
        state_pass = compare_variables(
            component=self.component,
            variables=STATE_VARIABLES,
            filename1=full_run,
            filename2=restart,
            logger=logger,
            config=self.config,
            ds1=self.open_model_dataset(full_run, self.config),
            ds2=self.open_model_dataset(restart, self.config),
        )

        if not (all_pass and state_pass):
            raise ValueError(
                f'Validation failed comparing the output of '
                f'{self.restart_subdir} with {self.full_run_subdir}.'
            )


def compare_datasets_exactly(ds1: xr.Dataset, ds2: xr.Dataset) -> List[str]:
    """
    Compare every variable in two datasets bit for bit

    Each variable must have the same dtype and the same bytes in both, so
    that ``-0.0`` differs from ``0.0`` and NaNs must have the same bit
    pattern.  The datasets should be opened with ``mask_and_scale=False``,
    so that fill values are compared as written rather than as NaNs.

    Parameters
    ----------
    ds1 : xarray.Dataset
        The first dataset

    ds2 : xarray.Dataset
        The second dataset

    Returns
    -------
    mismatches : list of str
        A description of each variable that is missing from one dataset or
        differs between them; empty if the datasets match
    """
    mismatches = []
    names1 = {str(name) for name in ds1.variables}
    names2 = {str(name) for name in ds2.variables}
    for name in sorted(names1 - names2):
        mismatches.append(f'{name} is only in the first dataset')
    for name in sorted(names2 - names1):
        mismatches.append(f'{name} is only in the second dataset')

    for name in sorted(names1 & names2):
        values1 = ds1[name].values
        values2 = ds2[name].values
        if values1.shape != values2.shape:
            mismatches.append(
                f'{name} has shape {values1.shape} and {values2.shape}'
            )
            continue
        if values1.dtype != values2.dtype:
            mismatches.append(
                f'{name} has dtype {values1.dtype} and {values2.dtype}'
            )
            continue
        different = _differing_points(values1, values2)
        if not np.any(different):
            continue
        message = (
            f'{name} differs at {np.count_nonzero(different)} of '
            f'{values1.size} points'
        )
        if np.issubdtype(values1.dtype, np.number):
            diff = np.abs(values1[different] - values2[different])
            message = f'{message}, by up to {np.max(diff):.6e}'
        mismatches.append(message)
    return mismatches


def _differing_points(values1: np.ndarray, values2: np.ndarray) -> np.ndarray:
    """
    Which points of two arrays of the same shape and dtype differ in their
    bytes, or in their values for arrays of Python objects
    """
    if values1.dtype.hasobject:
        return np.asarray(values1 != values2)
    bytes1 = np.ascontiguousarray(values1).view(np.uint8)
    bytes2 = np.ascontiguousarray(values2).view(np.uint8)
    shape = values1.shape + (values1.dtype.itemsize,)
    return np.any(bytes1.reshape(shape) != bytes2.reshape(shape), axis=-1)
