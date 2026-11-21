import numpy as np

from polaris.ocean.model import OceanIOStep
from polaris.tasks.ocean.realistic_global.min_level_cell.add_top_level import (
    VERTICAL_DIMS,
)

#: MPAS-Ocean's mixed-layer depths, whose searches down the column have to
#: start at the top active level
MLD_FILENAME = 'mixed_layer_depths.nc'

#: The files both runs write that are compared: the history and the
#: mixed-layer depths
COMPARED_FILES = ['output.nc', MLD_FILENAME]


def compare_shifted(ds_reference, ds_shifted, logger):
    """
    Check that a run with an inactive level above every column is bit-for-bit
    identical to the run without it, one level lower.

    Every variable of ``ds_reference`` is compared, ``xtime`` included, after
    the first level of ``ds_shifted`` is dropped.  The values have to be
    identical, NaN for NaN: unlike
    :py:func:`polaris.validate.compare_variables`, which skips a value that is
    not finite in either file, a NaN in only one run is a difference.

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
    all_pass = True
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

    for var in ds_reference.data_vars:
        if var not in ds_shifted:
            logger.error(f'  {var} is missing from the run with the top level')
            all_pass = False
            continue
        reference = ds_reference[var]
        shifted = ds_shifted[var]
        if reference.dims != shifted.dims or reference.shape != shifted.shape:
            logger.error(
                f'  {var} has dimensions {dict(shifted.sizes)} in the run '
                f'with the added level, but {dict(reference.sizes)} in the '
                f'reference run'
            )
            all_pass = False
            continue
        if not _compare_variable(var, reference, shifted, logger):
            all_pass = False

    return all_pass


class Compare(OceanIOStep):
    """
    A step that checks that the run with an inactive level above every column
    is bit-for-bit identical to the reference run, one level lower.

    Attributes
    ----------
    reference_subdir : str
        The subdirectory of the run without the added level

    shifted_subdir : str
        The subdirectory of the run with the added level
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
        for filename in COMPARED_FILES:
            for subdir in [reference_subdir, shifted_subdir]:
                self.add_input_file(
                    filename=f'{subdir}_{filename}',
                    target=f'../{subdir}/{filename}',
                )

    def run(self):
        """
        Compare each file the two runs wrote
        """
        logger = self.logger
        all_pass = True
        for filename in COMPARED_FILES:
            logger.info(f'Comparing {filename}:')
            ds_reference = self.open_model_dataset(
                f'{self.reference_subdir}_{filename}', decode_times=False
            )
            ds_shifted = self.open_model_dataset(
                f'{self.shifted_subdir}_{filename}', decode_times=False
            )
            if not compare_shifted(ds_reference, ds_shifted, logger):
                all_pass = False

        if not all_pass:
            raise ValueError(
                f'The run with an inactive level above every column, '
                f'{self.shifted_subdir}, is not bit-for-bit identical to '
                f'{self.reference_subdir}.'
            )
        logger.info(
            f'{self.shifted_subdir} is bit-for-bit identical to '
            f'{self.reference_subdir}.'
        )


def _compare_variable(var, reference, shifted, logger):
    """
    Compare one variable exactly, reporting how many values differ, by how
    much, and from which time index on

    Returns
    -------
    bool
        Whether the variable is identical in the two runs
    """
    ref_values = reference.values
    shifted_values = shifted.values
    if ref_values.dtype.kind in 'SUO':
        identical = np.array_equal(ref_values, shifted_values)
        differ = None
    else:
        differ = ref_values != shifted_values
        if ref_values.dtype.kind in 'fc':
            differ &= ~(np.isnan(ref_values) & np.isnan(shifted_values))
        identical = not differ.any()

    if identical:
        logger.info(f'  {var} PASS')
        return True

    if differ is None:
        logger.error(f'  {var} FAIL')
        return False

    count = int(differ.sum())
    diff = np.abs(ref_values[differ] - shifted_values[differ])
    finite = diff[np.isfinite(diff)]
    max_diff = f'{finite.max():.6g}' if finite.size > 0 else 'none finite'
    message = (
        f'  {var} FAIL: {count} of {differ.size} values differ, largest '
        f'difference {max_diff}'
    )
    if 'Time' in reference.dims:
        axis = reference.dims.index('Time')
        other_axes = tuple(i for i in range(differ.ndim) if i != axis)
        times = np.flatnonzero(differ.any(axis=other_axes))
        message = f'{message}, first at time index {times[0]}'
    logger.error(message)
    return False
