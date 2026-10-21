import os

import numpy as np
import xarray as xr

from polaris.ocean.model import OceanIOStep
from polaris.tasks.ocean.realistic_global.restart.restart_step import (
    BEFORE_RESTART_FILENAME,
)
from polaris.validate import compare_variables

#: The state variables compared between the full run and the restart run
VARIABLES = ['temperature', 'salinity', 'layerThickness', 'normalVelocity']


class Validate(OceanIOStep):
    """
    Check that a run continued from a restart writes the same history as the
    same run done in one go.

    Two things are checked, because a restart can go wrong in two ways.  The
    time axis has to hold every frame of the whole period, in increasing
    order: Omega #482 was a case where a continuing run silently overwrote
    the earlier frames instead of appending to them, leaving a file that was
    well formed and simply missing its first half.  The state then has to
    match the uninterrupted run, which is the usual exact-restart check.

    The history the restart run appended to is checked as well: it has to end
    before the full run's does, or there would have been nothing to append
    and the first check would pass without testing anything.

    Attributes
    ----------
    full_run_subdir : str
        Subdirectory of the step that ran the whole period in one go

    restart_subdir : str
        Subdirectory of the step that continued from a restart
    """

    def __init__(self, component, full_run_subdir, restart_subdir, indir):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        full_run_subdir : str
            Subdirectory of the step that ran the whole period in one go

        restart_subdir : str
            Subdirectory of the step that continued from a restart

        indir : str
            the directory the step is in, to which ``name`` will be appended
        """
        super().__init__(component=component, name='validate', indir=indir)

        self.full_run_subdir = full_run_subdir
        self.restart_subdir = restart_subdir

        for subdir in [full_run_subdir, restart_subdir]:
            self.add_input_file(
                filename=f'output_{subdir}.nc',
                target=f'../{subdir}/output.nc',
            )
        self.add_input_file(
            filename='output_before_restart.nc',
            target=f'../{full_run_subdir}/{BEFORE_RESTART_FILENAME}',
        )

    def run(self):
        """
        Compare the history of the restart run with the history of the
        uninterrupted run
        """
        super().run()
        logger = self.logger

        full_run = self.inputs[0]
        restart = self.inputs[1]
        before_restart = self.inputs[2]

        for filename in [full_run, restart, before_restart]:
            if not os.path.exists(filename):
                raise OSError(f'File {filename} does not exist.')

        before_pass = self._check_before_restart(full_run, before_restart)
        frames_pass = self._compare_time_axes(full_run, restart)

        ds1 = self.open_model_dataset(full_run, self.config)
        ds2 = self.open_model_dataset(restart, self.config)

        state_pass = compare_variables(
            component=self.component,
            variables=VARIABLES,
            filename1=full_run,
            filename2=restart,
            logger=logger,
            config=self.config,
            ds1=ds1,
            ds2=ds2,
        )

        if not (before_pass and frames_pass and state_pass):
            raise ValueError(
                f'Validation failed comparing the history of '
                f'{self.restart_subdir} with {self.full_run_subdir}.'
            )

    def _check_before_restart(self, full_run, before_restart):
        """
        Check that the history the restart run appended to holds the full
        run's first frames and ends before the full run's does

        Returns
        -------
        bool
            Whether the history before the restart is a strict leading part
            of the full run's
        """
        logger = self.logger

        with xr.open_dataset(full_run, decode_times=False) as ds:
            expected = ds.time.values
        with xr.open_dataset(before_restart, decode_times=False) as ds:
            actual = ds.time.values

        if actual.size == 0 or actual.size >= expected.size:
            logger.error(
                f'The history before the restart has {actual.size} frames, '
                f'but it should have fewer than the {expected.size} of the '
                f'full run, or the restart run has nothing to append to.'
            )
            return False
        if not np.allclose(actual, expected[: actual.size]):
            logger.error(
                f'The history before the restart does not start the way the '
                f"full run's does.\n"
                f'  full run:       {expected}\n'
                f'  before restart: {actual}'
            )
            return False

        logger.info(
            f'  history before the restart PASS ({actual.size} of '
            f'{expected.size} frames)'
        )
        return True

    def _compare_time_axes(self, full_run, restart):
        """
        Check that the restart run's history has every frame the full run's
        does, and that its frames increase in time

        Returns
        -------
        bool
            Whether the time axes agree
        """
        logger = self.logger

        # read the elapsed-time coordinate as the model wrote it, rather than
        # through the Omega-to-MPAS-Ocean renaming, since it is the variable
        # under test
        with xr.open_dataset(full_run, decode_times=False) as ds:
            expected = ds.time.values
        with xr.open_dataset(restart, decode_times=False) as ds:
            actual = ds.time.values

        all_pass = True

        if actual.size < expected.size:
            logger.error(
                f"The restart run's history has {actual.size} frames but "
                f"the full run's has {expected.size}.  Frames written before "
                f'the restart appear to have been overwritten rather than '
                f'appended to (see Omega #482).'
            )
            all_pass = False
        elif actual.size != expected.size:
            logger.error(
                f"The restart run's history has {actual.size} frames but "
                f"the full run's has {expected.size}."
            )
            all_pass = False
        elif not np.allclose(actual, expected):
            logger.error(
                f"The restart run's history frames are at different times "
                f"than the full run's.\n"
                f'  full run:    {expected}\n'
                f'  restart run: {actual}'
            )
            all_pass = False

        if actual.size > 1 and not np.all(np.diff(actual) > 0):
            logger.error(
                f'The history times of the restart run do not increase: '
                f'{actual}'
            )
            all_pass = False

        if all_pass:
            logger.info(
                f'  history time axis PASS ({actual.size} frames, '
                f'{actual[0]} to {actual[-1]} s)'
            )

        return all_pass
