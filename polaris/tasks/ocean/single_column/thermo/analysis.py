import numpy as np
import xarray as xr

from polaris.constants import get_constant
from polaris.ocean.model import OceanIOStep, get_days_since_start

# Omega hard-codes the TEOS-10 reference specific heat of seawater in
# GlobalConstants.h (Cp0Sw = 1 / HFluxFac / RhoSw).  This differs from the PCD
# value ``seawater_specific_heat_capacity_reference`` so it is reproduced here
# to keep the heat budget consistent with what the model actually integrates.
CP0_SW = 3991.86795711963

# Freshwater/mass fluxes that Omega adds to the (pseudo-)thickness equation in
# ``SfcThicknessForcingOnCell`` (TendencyTerms.h).  ``seaIceSalinityFlux`` also
# enters the thickness equation, so it appears in the mass budget as well as
# the salt budget below.
MASS_FLUX_VARS = [
    'snowFlux',
    'rainFlux',
    'evaporationFlux',
    'seaIceFreshWaterFlux',
    'iceRunoffFlux',
    'riverRunoffFlux',
    'seaIceSalinityFlux',
]

# Direct heat fluxes that Omega adds to the temperature equation in
# ``SfcTracerForcingOnCell``.  Note this excludes the enthalpy carried by mass
# fluxes (rain/river/snow/ice-runoff), which is handled by the enthalpy skip
# logic below.
HEAT_FLUX_VARS = [
    'latentHeatFlux',
    'sensibleHeatFlux',
    'shortWaveHeatFlux',
    'longWaveHeatFluxUp',
    'longWaveHeatFluxDown',
    'seaIceHeatFlux',
]

# Salt flux added to the salinity equation.
SALT_FLUX_VARS = ['seaIceSalinityFlux']

# Mass fluxes that also carry an SST-/freezing-point-dependent enthalpy heat
# flux in Omega's ``SfcTracerForcingOnCell``.  When any of these is active the
# heat content changes by an amount that is not captured by ``HEAT_FLUX_VARS``
# alone, so the heat budget is skipped for those runs (per-budget check).
ENTHALPY_FLUX_VARS = [
    'rainFlux',
    'riverRunoffFlux',
    'snowFlux',
    'iceRunoffFlux',
]


class Analysis(OceanIOStep):
    """
    A step that verifies conservation of mass, heat and salt for each of the
    ``thermo`` forward runs.  For every forward run (each driven by a single
    surface forcing variable) the change in the column-integrated content is
    compared against the surface forcing flux accumulated over the run.

    Attributes
    ----------
    comparisons : dict
        A mapping from a forcing-variable name to the (relative) path of the
        corresponding forward step.
    """

    def __init__(self, component, indir, init, comparisons):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        indir : str
            The subdirectory that the task belongs to, that this step will
            go into a subdirectory of

        init : polaris.Step
            The initial-condition step providing the mesh (all forward runs
            share an identical mesh)

        comparisons : dict
            A mapping from a forcing-variable name to the (relative) path of
            the corresponding forward step
        """
        super().__init__(component=component, name='analysis', indir=indir)
        self.comparisons = dict(comparisons)
        self.add_input_file(
            filename='mesh.nc', work_dir_target=f'{init.path}/culled_mesh.nc'
        )
        for name, path in self.comparisons.items():
            self.add_input_file(
                filename=f'init_{name}.nc', target=f'{path}/init.nc'
            )
            self.add_input_file(
                filename=f'output_{name}.nc', target=f'{path}/output.nc'
            )
            self.add_input_file(
                filename=f'forcing_{name}.nc', target=f'{path}/forcing.nc'
            )

    def run(self):
        """
        Run this step of the test case
        """
        config = self.config
        logger = self.logger
        tol = config.getfloat(
            'single_column_thermo', 'conservation_error_tolerance'
        )
        rho_sw = get_constant('seawater_density_reference')

        # areaCell is identical for all forward runs (shared mesh); the mesh
        # file contains no thickness/tracer fields so no reconstruction occurs.
        ds_mesh = self.open_model_dataset('mesh.nc', config=config)
        area = ds_mesh['areaCell'].values.astype(float)

        all_passed = True
        for name in self.comparisons.keys():
            passed = self._check_run(name, area, rho_sw, tol, logger)
            all_passed = all_passed and passed

        if not all_passed:
            raise ValueError(
                'Conservation check failed: the accumulated surface forcing '
                'flux does not match the change in column content within the '
                f'tolerance ({tol:g}).  See the log above for details.'
            )

    def _check_run(self, name, area, rho_sw, tol, logger):
        """
        Check mass, heat and salt conservation for a single forward run.

        Returns ``True`` if all checked budgets are within tolerance.
        """
        config = self.config

        # Read the prognostic state directly (native names) to use the
        # mass-based pseudo-thickness that Omega actually integrates, rather
        # than the geometric thickness reconstructed by ``open_model_dataset``.
        # MPAS-Ocean (Boussinesq) has no pseudo-thickness, so its geometric
        # ``layerThickness`` is used instead.  The initial condition (t=0) is
        # taken from ``init.nc`` and the final state from the last snapshot of
        # ``output.nc`` so the full run duration is verified.
        ds_init = xr.open_dataset(f'init_{name}.nc', decode_times=False)
        ds_out = xr.open_dataset(f'output_{name}.nc', decode_times=False)

        # elapsed time from the initial condition (t=0) to the final snapshot
        dt = _elapsed_seconds(ds_out)

        # column-integrated content per cell (mass, heat, salt) at t=0 and at
        # the final snapshot
        h0, ht0, hs0 = _column_content(ds_init, time_index=0)
        h1, ht1, hs1 = _column_content(ds_out, time_index=-1)

        # measured change in total column content (summed over the domain)
        measured_mass = np.sum(rho_sw * area * (h1 - h0))
        measured_heat = np.sum(rho_sw * CP0_SW * area * (ht1 - ht0))
        measured_salt = np.sum((rho_sw / 1000.0) * area * (hs1 - hs0))

        # initial total column content, used as the normalization floor for
        # budgets that have no expected flux
        mass_scale = np.sum(rho_sw * area * h0)
        heat_scale = np.sum(rho_sw * CP0_SW * area * ht0)
        salt_scale = np.sum((rho_sw / 1000.0) * area * hs0)

        # accumulated surface forcing flux over the run (forcing is constant in
        # time and uniform in space)
        ds_forcing = self.open_model_dataset(
            f'forcing_{name}.nc', config=config
        )
        fluxes = {
            var: _surface_field(ds_forcing, var)
            for var in set(MASS_FLUX_VARS + HEAT_FLUX_VARS + SALT_FLUX_VARS)
        }

        def _accumulated(var_list):
            total_per_cell = np.zeros_like(area)
            for var in var_list:
                if fluxes[var] is not None:
                    total_per_cell = total_per_cell + fluxes[var]
            return np.sum(total_per_cell * area * dt)

        expected_mass = _accumulated(MASS_FLUX_VARS)
        expected_heat = _accumulated(HEAT_FLUX_VARS)
        expected_salt = _accumulated(SALT_FLUX_VARS)

        # skip the heat budget for runs with an enthalpy-carrying mass flux
        skip_heat = any(
            fluxes[var] is not None and np.any(fluxes[var] != 0.0)
            for var in ENTHALPY_FLUX_VARS
        )

        logger.info(f'Conservation check for forcing "{name}" (dt={dt:g} s):')

        passed = True
        passed = (
            self._report_budget(
                'mass', measured_mass, expected_mass, mass_scale, tol, logger
            )
            and passed
        )
        if skip_heat:
            logger.info(
                '    heat: skipped (mass flux carries an SST-dependent '
                'enthalpy heat flux not accounted for in this check)'
            )
        else:
            passed = (
                self._report_budget(
                    'heat',
                    measured_heat,
                    expected_heat,
                    heat_scale,
                    tol,
                    logger,
                )
                and passed
            )
        passed = (
            self._report_budget(
                'salt', measured_salt, expected_salt, salt_scale, tol, logger
            )
            and passed
        )
        return passed

    @staticmethod
    def _report_budget(label, measured, expected, scale, tol, logger):
        """
        Log a single budget and return whether it is within tolerance.

        For a driven budget (nonzero expected flux) the error is relative to
        the accumulated flux, ``|measured - expected| / |expected|``.  For a
        budget with no expected flux the residual is instead compared against a
        floor set by the same tolerance times the initial total column content
        (``|measured| / scale``), so a single relative tolerance applies to
        every budget.
        """
        abs_diff = abs(measured - expected)
        if expected != 0.0:
            error = abs_diff / abs(expected)
            basis = 'rel. to flux'
        elif scale != 0.0:
            error = abs_diff / abs(scale)
            basis = 'rel. to content'
        else:
            error = abs_diff
            basis = 'absolute'
        status = 'PASS' if error <= tol else 'FAIL'
        logger.info(
            f'    {label}: measured={measured:.6e} expected={expected:.6e} '
            f'error={error:.3e} ({basis}) [{status}]'
        )
        return error <= tol


def _pick(ds, *names):
    """Return the first variable in ``names`` present in ``ds``."""
    for name in names:
        if name in ds:
            return ds[name]
    raise KeyError(
        f'None of {names} found in dataset (available: {list(ds.data_vars)})'
    )


def _column_content(ds, time_index):
    """
    Return per-cell column-integrated ``(h, h*T, h*S)`` at the given time
    index as 1D numpy arrays, using the mass-based pseudo-thickness when
    present (Omega) and the geometric layer thickness otherwise (MPAS-Ocean).
    """
    thickness = _pick(ds, 'PseudoThickness', 'layerThickness')
    temperature = _pick(ds, 'Temperature', 'temperature')
    salinity = _pick(ds, 'Salinity', 'salinity')

    dims = thickness.dims
    vert_dim = 'NVertLayers' if 'NVertLayers' in dims else 'nVertLevels'

    def _at_time(da):
        for time_dim in ('time', 'Time'):
            if time_dim in da.dims:
                da = da.isel({time_dim: time_index})
                break
        return da

    thickness = _at_time(thickness)
    temperature = _at_time(temperature)
    salinity = _at_time(salinity)

    col_h = thickness.sum(dim=vert_dim).values.astype(float)
    col_ht = (thickness * temperature).sum(dim=vert_dim).values.astype(float)
    col_hs = (thickness * salinity).sum(dim=vert_dim).values.astype(float)
    return col_h, col_ht, col_hs


def _surface_field(ds, name):
    """
    Return a per-cell surface forcing field as a 1D numpy array, or ``None``
    if the variable is absent.  A leading time dimension (if any) is dropped.
    """
    if name not in ds:
        return None
    da = ds[name]
    if 'Time' in da.dims:
        da = da.isel(Time=0)
    elif 'time' in da.dims:
        da = da.isel(time=0)
    return da.values.astype(float)


def _elapsed_seconds(ds):
    """
    Return the elapsed time in seconds from the start of the simulation (the
    time of the initial condition) to the final snapshot of ``ds``.  Omega
    writes a numeric ``time`` variable holding elapsed seconds since the start
    of the simulation; MPAS-Ocean writes ``daysSinceStartOfSim``.
    """
    if 'daysSinceStartOfSim' in ds:
        days = ds['daysSinceStartOfSim'].values.astype(float)
        return float(days[-1]) * 86400.0
    if 'time' in ds.variables:
        t = np.asarray(ds['time'].values)
        if np.issubdtype(t.dtype, np.number):
            return float(t[-1])
    t_days = get_days_since_start(ds)
    return float(t_days[-1] * 86400.0)
