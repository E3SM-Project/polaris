from typing import List, Tuple

import numpy as np
import xarray as xr

from polaris.ocean.model import OceanIOStep
from polaris.tasks.ocean.realistic_global.min_level_cell.add_top_level import (
    LEVEL_INDEX_VARS,
    VERTICAL_DIMS,
)

#: MPAS-Ocean's mixed-layer depths, whose searches down the column have to
#: start at the top active level
MLD_FILENAME = 'mixed_layer_depths.nc'

#: The history file every run writes
OUTPUT_FILENAME = 'output.nc'

#: The time dimension, by its MPAS-Ocean and Omega names
TIME_DIMS = ['Time', 'time']


def compare_shifted(ds_reference, ds_shifted, logger):
    """
    Check that a run with an inactive level above every column is bit-for-bit
    identical to the run without it, one level lower.

    Every variable of ``ds_reference`` is compared, ``xtime`` included, after
    the first level of ``ds_shifted`` is dropped and any level index in it is
    moved back up by one.  The values have to be identical, NaN for NaN:
    unlike :py:func:`polaris.validate.compare_variables`, which skips a value
    that is not finite in either file, a NaN in only one run is a difference.

    Parameters
    ----------
    ds_reference : xarray.Dataset
        The output of the run without the added level

    ds_shifted : xarray.Dataset
        The output of the run with the added level

    logger : logging.Logger
        The logger to report the comparison to

    Returns
    -------
    bool
        Whether the two runs are bit-for-bit identical
    """
    for dim in VERTICAL_DIMS:
        if dim not in ds_reference.dims:
            continue
        expected = ds_reference.sizes[dim] + 1
        actual = ds_shifted.sizes.get(dim)
        if actual != expected:
            logger.error(
                f'The run with the added level has {dim} = {actual}, but it '
                f'should have one more than the reference run, {expected}.'
            )
            return False
        ds_shifted = ds_shifted.isel({dim: slice(1, None)})

    for var in LEVEL_INDEX_VARS:
        if var in ds_shifted:
            index = ds_shifted[var]
            ds_shifted[var] = xr.where(index > 0, index - 1, index).astype(
                index.dtype
            )

    return compare_identical(ds_reference, ds_shifted, logger)


def compare_identical(ds_reference, ds_other, logger):
    """
    Check that two runs are bit-for-bit identical, NaN for NaN, in every
    variable of ``ds_reference``

    Parameters
    ----------
    ds_reference : xarray.Dataset
        The output of one run

    ds_other : xarray.Dataset
        The output of the run that has to match it

    logger : logging.Logger
        The logger to report the comparison to

    Returns
    -------
    bool
        Whether the two runs are bit-for-bit identical
    """
    all_pass = True
    for var in ds_reference.data_vars:
        if var not in ds_other:
            logger.error(f'  {var} is missing from the run being compared')
            all_pass = False
            continue
        reference = ds_reference[var]
        other = ds_other[var]
        if reference.dims != other.dims or reference.shape != other.shape:
            logger.error(
                f'  {var} has dimensions {dict(other.sizes)} in the run '
                f'being compared, but {dict(reference.sizes)} in the '
                f'reference run'
            )
            all_pass = False
            continue
        if not _compare_variable(var, reference, other, logger):
            all_pass = False

    return all_pass


class Compare(OceanIOStep):
    """
    A step that checks that the run with an inactive level above every column
    is bit-for-bit identical to the reference run, one level lower, and that
    any run continued from a restart of it is identical to it

    The task sets which runs and files are compared in its ``configure()``,
    once the model is known, since Omega neither writes MPAS-Ocean's
    mixed-layer depths nor runs MPAS-Ocean's restart.

    Attributes
    ----------
    reference_subdir : str
        The subdirectory of the run without the added level

    shifted_subdir : str
        The subdirectory of the run with the added level

    restart_subdir : str or None
        The subdirectory of the run continued from a restart of the run with
        the added level, if there is one

    filenames : list of str
        The files each run writes that are compared
    """

    def __init__(self, component, indir, reference_subdir, shifted_subdir):
        """
        Create the step

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the step belongs to

        indir : str
            The directory the step is in, to which ``name`` is appended

        reference_subdir : str
            The subdirectory of the run without the added level

        shifted_subdir : str
            The subdirectory of the run with the added level
        """
        super().__init__(component=component, name='compare', indir=indir)
        self.reference_subdir = reference_subdir
        self.shifted_subdir = shifted_subdir
        self.restart_subdir: str | None = None
        self.filenames: List[str] = [OUTPUT_FILENAME]

    def setup(self):
        """
        Link each file the runs write that is compared
        """
        super().setup()
        links = set()
        for subdir_a, subdir_b, _ in self._comparisons():
            for subdir in [subdir_a, subdir_b]:
                for filename in self.filenames:
                    link = f'{subdir}_{filename}'
                    if link in links:
                        continue
                    links.add(link)
                    self.add_input_file(
                        filename=link, target=f'../{subdir}/{filename}'
                    )

    def run(self):
        """
        Compare each file the runs wrote
        """
        logger = self.logger
        failed = []
        for subdir_a, subdir_b, shifted in self._comparisons():
            all_pass = True
            for filename in self.filenames:
                logger.info(
                    f'Comparing {subdir_b} with {subdir_a}, {filename}:'
                )
                ds_a = xr.open_dataset(
                    f'{subdir_a}_{filename}', decode_times=False
                )
                ds_b = xr.open_dataset(
                    f'{subdir_b}_{filename}', decode_times=False
                )
                if shifted:
                    passed = compare_shifted(ds_a, ds_b, logger)
                else:
                    passed = compare_identical(ds_a, ds_b, logger)
                if not passed:
                    all_pass = False
            if all_pass:
                logger.info(
                    f'{subdir_b} is bit-for-bit identical to {subdir_a}.'
                )
            else:
                failed.append(f'{subdir_b} with {subdir_a}')

        if failed:
            raise ValueError(
                f'These runs are not bit-for-bit identical: '
                f'{"; ".join(failed)}.'
            )

    def _comparisons(self) -> List[Tuple[str, str, bool]]:
        """
        The pairs of runs to compare, and whether the second has the added
        level and the first does not
        """
        comparisons = [(self.reference_subdir, self.shifted_subdir, True)]
        if self.restart_subdir is not None:
            comparisons.append(
                (self.shifted_subdir, self.restart_subdir, False)
            )
        return comparisons


def _compare_variable(var, reference, other, logger):
    """
    Compare one variable exactly, reporting how many values differ, by how
    much, and from which time index on

    Returns
    -------
    bool
        Whether the variable is identical in the two runs
    """
    ref_values = reference.values
    other_values = other.values
    if ref_values.dtype.kind in 'SUO':
        identical = np.array_equal(ref_values, other_values)
        differ = None
    else:
        differ = ref_values != other_values
        if ref_values.dtype.kind in 'fc':
            differ &= ~(np.isnan(ref_values) & np.isnan(other_values))
        identical = not differ.any()

    if identical:
        logger.info(f'  {var} PASS')
        return True

    if differ is None:
        logger.error(f'  {var} FAIL')
        return False

    count = int(differ.sum())
    diff = np.abs(ref_values[differ] - other_values[differ])
    finite = diff[np.isfinite(diff)]
    max_diff = f'{finite.max():.6g}' if finite.size > 0 else 'none finite'
    message = (
        f'  {var} FAIL: {count} of {differ.size} values differ, largest '
        f'difference {max_diff}'
    )
    for time_dim in TIME_DIMS:
        if time_dim in reference.dims:
            axis = reference.dims.index(time_dim)
            other_axes = tuple(i for i in range(differ.ndim) if i != axis)
            times = np.flatnonzero(differ.any(axis=other_axes))
            message = f'{message}, first at time index {times[0]}'
            break
    logger.error(message)
    return False
