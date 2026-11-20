import glob
import os
import shutil

import netCDF4
import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf

from polaris import Step
from polaris.landice.mismip_plus.diagnostics import compute_diagnostics
from polaris.tasks.landice.mismip_plus.output import read_output
from polaris.tasks.landice.mismip_plus.spin_up.run import (
    OUTPUT_INTERVAL_YEARS,
)

# the protocol's position (km) for the steady state's grounding line on the
# centerline, and how far from it the steady state may be
GL_TARGET = 450.0
GL_TARGET_TOLERANCE = 10.0

# MALI's gravity in m s^-2, which it also passes to Albany
GRAVITY = 9.80616


class SpinUp(Step):
    """
    A step for checking that the spin-up has converged to the MISMIP+ steady
    state and for writing the steady state
    """

    def __init__(self, component, run_step, subdir):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        run_step : polaris.tasks.landice.mismip_plus.spin_up.SpinUpRun
            The step that runs MALI

        subdir : str
            The subdirectory for the step
        """
        super().__init__(component=component, name='spin_up', subdir=subdir)
        # the spin-up takes thousands of model years, so other tasks read
        # the steady state from the cache by default
        self.default_cached = True
        # MALI's output and restarts are found when it has run, so the step
        # links the whole run directory
        self.add_input_file(filename='run', work_dir_target=run_step.path)
        self.add_dependency(run_step, run_step.name)
        for filename in ['steady_state.nc', 'spin_up_diagnostics.nc']:
            self.add_output_file(filename=filename)

    def run(self):
        """
        Run this step
        """
        logger = self.logger
        section = self.config['mismip_plus_spin_up']
        run_years = section.getint('run_years')
        convergence_years = section.getint('convergence_years')
        gl_tolerance = section.getfloat('gl_tolerance')
        vaf_tolerance = section.getfloat('vaf_tolerance')
        if convergence_years % OUTPUT_INTERVAL_YEARS != 0:
            raise ValueError(
                f'convergence_years must be a multiple of '
                f'{OUTPUT_INTERVAL_YEARS}'
            )
        if convergence_years > run_years:
            raise ValueError('convergence_years is longer than run_years')

        run_dir = os.path.realpath('run')
        restarts = _get_restarts(run_dir)
        if run_years not in restarts:
            raise ValueError(
                f'The spin-up has no restart at year {run_years}.  Rerun the '
                f'step in {run_dir} to continue it.'
            )

        ds_diag = _compute_time_series(run_dir, run_years)
        write_netcdf(ds_diag, 'spin_up_diagnostics.nc')

        end = ds_diag.sel(Time=float(run_years))
        start = ds_diag.sel(Time=float(run_years - convergence_years))
        x_gl = 1e-3 * float(end.xGL)
        gl_change = 1e-3 * abs(float(end.xGL - start.xGL))
        vaf_change = abs(float((end.iceVAF - start.iceVAF) / start.iceVAF))
        logger.info(
            f'Over the last {convergence_years} years of {run_years}, the '
            f'grounding line moved {gl_change:.3g} km to {x_gl:.2f} km and '
            f'the volume above flotation changed by {vaf_change:.3g} of '
            f'itself'
        )
        if gl_change >= gl_tolerance or vaf_change >= vaf_tolerance:
            raise ValueError(
                f'The spin-up has not converged: over its last '
                f'{convergence_years} years, the grounding line moved '
                f'{gl_change:.3g} km (tolerance {gl_tolerance:g} km) and the '
                f'volume above flotation changed by {vaf_change:.3g} '
                f'(tolerance {vaf_tolerance:g}).  Increase run_years in the '
                f'[mismip_plus_spin_up] config section and rerun the step in '
                f'{run_dir} to continue it.'
            )
        if abs(x_gl - GL_TARGET) > GL_TARGET_TOLERANCE:
            raise ValueError(
                f'The steady state grounding line on the centerline is at '
                f'{x_gl:.2f} km, outside {GL_TARGET:g} +/- '
                f'{GL_TARGET_TOLERANCE:g} km.  Change flow_param_a in the '
                f'[mismip_plus] config section and continue the spin-up.'
            )

        self._write_steady_state(restarts[run_years], end, run_years)

    def _write_steady_state(self, restart_filename, diagnostics, run_years):
        """
        Copy the final restart to the steady state and describe it in its
        global attributes
        """
        shutil.copyfile(restart_filename, 'steady_state.nc')
        initial_state = self.config.get('mismip_plus_spin_up', 'initial_state')
        with open('run/albany_input.yaml') as albany_file:
            albany_input = albany_file.read()
        attrs = {
            'mismip_plus_initial_state': initial_state,
            'mismip_plus_spin_up_years': np.int32(run_years),
            'mismip_plus_gravity': GRAVITY,
            'mismip_plus_grounding_line_x': float(diagnostics.xGL),
            'mismip_plus_ice_volume': float(diagnostics.iceVolume),
            'mismip_plus_volume_above_flotation': float(diagnostics.iceVAF),
            'mismip_plus_grounded_area': float(diagnostics.groundedArea),
            'mismip_plus_albany_input': albany_input,
        }
        with netCDF4.Dataset('steady_state.nc', 'a') as ds:
            ds.setncatts(attrs)


def _get_restarts(run_dir):
    """
    Get the restarts in a run directory, keyed by year
    """
    restarts = dict()
    for filename in glob.glob(os.path.join(run_dir, 'restart.*.nc')):
        year = os.path.basename(filename).split('.')[1]
        restarts[int(year)] = filename
    return restarts


def _compute_time_series(run_dir, run_years):
    """
    Compute the diagnostics of each snapshot in MALI's output up to the end
    of the spin-up
    """
    with xr.open_dataset(os.path.join(run_dir, 'landice_grid.nc')) as ds:
        ds_mesh = ds[['areaCell', 'xCell', 'yCell', 'dcEdge']].load()
    ds = read_output(os.path.join(run_dir, 'output.nc'))
    ds = ds[['thickness', 'bedTopography']].sel(
        Time=slice(None, float(run_years))
    )
    ds_diag = compute_diagnostics(ds, ds_mesh=ds_mesh)
    ds_diag['Time'] = ds.Time
    return ds_diag
