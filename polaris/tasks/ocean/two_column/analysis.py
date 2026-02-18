import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

from polaris.ocean.model import OceanIOStep
from polaris.ocean.vertical.ztilde import Gravity
from polaris.viz import use_mplstyle


class Analysis(OceanIOStep):
    """
    A step for analyzing two-column HPGA errors versus a reference solution
    and versus the Python-computed initial-state solution.

    Attributes
    ----------
    dependencies_dict : dict
        A dictionary of dependent steps:

        reference : polaris.Step
            The reference step that produces ``reference_solution.nc``

        init : dict
            Mapping from horizontal resolution (km) to ``Init`` step

        forward : dict
            Mapping from horizontal resolution (km) to ``Forward`` step
    """

    def __init__(self, component, indir, dependencies):
        """
        Create the analysis step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        indir : str
            The subdirectory that the task belongs to, that this step will
            go into a subdirectory of

        dependencies : dict
            A dictionary of dependent steps
        """
        super().__init__(component=component, name='analysis', indir=indir)

        self.dependencies_dict = dependencies

        self.add_output_file('omega_vs_reference.png')
        self.add_output_file('omega_vs_reference.nc')
        self.add_output_file('omega_vs_python.png')
        self.add_output_file('omega_vs_python.nc')

    def setup(self):
        """
        Add inputs from reference, init and forward steps
        """
        super().setup()

        section = self.config['two_column']
        horiz_resolutions = section.getexpression('horiz_resolutions')
        assert horiz_resolutions is not None

        reference = self.dependencies_dict['reference']
        self.add_input_file(
            filename='reference_solution.nc',
            work_dir_target=f'{reference.path}/reference_solution.nc',
        )

        init_steps = self.dependencies_dict['init']
        forward_steps = self.dependencies_dict['forward']
        for resolution in horiz_resolutions:
            init = init_steps[resolution]
            forward = forward_steps[resolution]
            self.add_input_file(
                filename=f'init_r{resolution:02g}.nc',
                work_dir_target=f'{init.path}/initial_state.nc',
            )
            self.add_input_file(
                filename=f'output_r{resolution:02g}.nc',
                work_dir_target=f'{forward.path}/output.nc',
            )

    def run(self):
        """
        Run this step of the test case
        """
        plt.switch_backend('Agg')
        logger = self.logger
        config = self.config

        rho0 = config.getfloat('vertical_grid', 'rho0')
        assert rho0 is not None, (
            'The "rho0" configuration option must be set in the '
            '"vertical_grid" section.'
        )

        section = config['two_column']
        horiz_resolutions = section.getexpression('horiz_resolutions')
        assert horiz_resolutions is not None, (
            'The "horiz_resolutions" configuration option must be set in '
            'the "two_column" section.'
        )
        omega_vs_polaris_norm_rmse_threshold = section.getfloat(
            'omega_vs_polaris_norm_rmse_threshold'
        )
        assert omega_vs_polaris_norm_rmse_threshold is not None, (
            'The "omega_vs_polaris_norm_rmse_threshold" configuration '
            'option must be set in the "two_column" section.'
        )
        omega_vs_reference_high_res_norm_rmse_threshold = section.getfloat(
            'omega_vs_reference_high_res_norm_rmse_threshold'
        )
        assert omega_vs_reference_high_res_norm_rmse_threshold is not None, (
            'The "omega_vs_reference_high_res_norm_rmse_threshold" '
            'configuration option must be set in the "two_column" section.'
        )
        omega_vs_reference_convergence_rate_min = section.getfloat(
            'omega_vs_reference_convergence_rate_min'
        )
        assert omega_vs_reference_convergence_rate_min is not None, (
            'The "omega_vs_reference_convergence_rate_min" configuration '
            'option must be set in the "two_column" section.'
        )
        omega_vs_reference_convergence_rate_max = section.getfloat(
            'omega_vs_reference_convergence_rate_max'
        )
        assert omega_vs_reference_convergence_rate_max is not None, (
            'The "omega_vs_reference_convergence_rate_max" configuration '
            'option must be set in the "two_column" section.'
        )

        ds_ref = self.open_model_dataset('reference_solution.nc')
        if ds_ref.sizes.get('nCells', 0) <= 2:
            raise ValueError(
                'The reference solution requires at least 3 columns so that '
                'the central column is nCells=2.'
            )

        ref_z = ds_ref.ZTildeInter.isel(Time=0, nCells=2).values
        ref_hpga = ds_ref.HPGAInter.isel(Time=0).values
        ref_valid_grad_mask = ds_ref.ValidGradInterMask.isel(Time=0).values

        ref_errors = []
        ref_norm_errors = []
        py_errors = []

        for resolution in horiz_resolutions:
            ds_init = self.open_model_dataset(f'init_r{resolution:02g}.nc')
            ds_out = self.open_model_dataset(
                f'output_r{resolution:02g}.nc', decode_times=False
            )

            edge_index, cells_on_edge = _get_internal_edge(ds_init)
            cell0, cell1 = cells_on_edge

            z_tilde_forward = _get_forward_z_tilde_edge_mid(
                ds_out=ds_out,
                rho0=rho0,
                cell0=cell0,
                cell1=cell1,
            )
            hpga_forward = ds_out.NormalVelocityTend.isel(
                Time=0, nEdges=edge_index
            ).values

            # maxLevelCell is one-based (Fortran indexing), convert to
            # zero-based and use the shallowest valid bottom among the two
            # cells that bound the internal edge.
            max_level_cells = ds_init.maxLevelCell.isel(
                nCells=[cell0, cell1]
            ).values.astype(int)
            max_level_index = int(np.min(max_level_cells) - 1)
            if max_level_index < 0:
                raise ValueError(
                    f'Invalid maxLevelCell values {max_level_cells} at '
                    f'resolution {resolution:g} km.'
                )

            forward_valid_mask = np.zeros_like(hpga_forward, dtype=bool)
            forward_valid_mask[: max_level_index + 1] = True

            sampled_ref_hpga = _sample_reference_without_interpolation(
                ref_z=ref_z,
                ref_values=ref_hpga,
                target_z=z_tilde_forward,
                ref_valid_mask=ref_valid_grad_mask,
                target_valid_mask=forward_valid_mask,
            )

            hpga_ref_diff = hpga_forward - sampled_ref_hpga
            ref_errors.append(_rms_error(hpga_ref_diff))
            ref_norm_errors.append(
                _normalized_rms_error(
                    values=hpga_ref_diff,
                    reference_values=sampled_ref_hpga,
                )
            )

            z_tilde_init = (
                0.5
                * (
                    ds_init.ZTildeMid.isel(Time=0, nCells=cell0)
                    + ds_init.ZTildeMid.isel(Time=0, nCells=cell1)
                ).values
            )
            _check_vertical_match(
                z_ref=z_tilde_init,
                z_test=z_tilde_forward,
                msg=(
                    'ZTilde mismatch between Python init and Omega forward '
                    f'at resolution {resolution:g} km'
                ),
                valid_mask=forward_valid_mask,
            )

            hpga_init = ds_init.HPGA.isel(Time=0).values
            hpga_diff = hpga_forward - hpga_init
            py_errors.append(
                _normalized_rms_error(
                    values=hpga_diff,
                    reference_values=hpga_init,
                    valid_mask=forward_valid_mask,
                )
            )

        resolution_array = np.asarray(horiz_resolutions, dtype=float)
        ref_error_array = np.asarray(ref_errors, dtype=float)
        ref_norm_error_array = np.asarray(ref_norm_errors, dtype=float)
        py_error_array = np.asarray(py_errors, dtype=float)

        ref_fit, ref_slope, ref_intercept = _power_law_fit(
            x=resolution_array,
            y=ref_error_array,
        )

        _write_dataset(
            filename='omega_vs_reference.nc',
            resolution_km=resolution_array,
            rms_error=ref_error_array,
            fit=ref_fit,
            slope=ref_slope,
            intercept=ref_intercept,
            y_name='rms_error_vs_reference',
            y_units='m s-2',
        )
        _write_dataset(
            filename='omega_vs_python.nc',
            resolution_km=resolution_array,
            rms_error=py_error_array,
            y_name='rms_error_vs_python',
            y_units='1',
        )

        _plot_errors(
            resolution_km=resolution_array,
            rms_error=ref_error_array,
            fit=ref_fit,
            slope=ref_slope,
            y_label='RMS error in HPGA (m s-2)',
            title='Omega HPGA Error vs Reference Solution',
            output='omega_vs_reference.png',
        )
        _plot_errors(
            resolution_km=resolution_array,
            rms_error=py_error_array,
            y_label='Normalized RMS difference in HPGA',
            title='Omega vs Polaris HPGA Difference',
            output='omega_vs_python.png',
        )

        logger.info(f'Omega-vs-reference convergence slope: {ref_slope:1.3f}')
        logger.info(
            'Omega-vs-Polaris normalized RMS differences by resolution: '
            f'{dict(zip(resolution_array, py_error_array, strict=True))}'
        )

        failing_polaris = py_error_array > omega_vs_polaris_norm_rmse_threshold
        if np.any(failing_polaris):
            failing_text = ', '.join(
                [
                    f'{resolution_array[index]:g} km: '
                    f'{py_error_array[index]:.3e}'
                    for index in np.where(failing_polaris)[0]
                ]
            )
            raise ValueError(
                'Omega-vs-Polaris normalized RMS difference exceeds '
                'omega_vs_polaris_norm_rmse_threshold '
                f'({omega_vs_polaris_norm_rmse_threshold:.3e}) at: '
                f'{failing_text}'
            )

        highest_resolution_index = int(np.argmin(resolution_array))
        highest_resolution = float(resolution_array[highest_resolution_index])
        highest_resolution_norm_ref_error = float(
            ref_norm_error_array[highest_resolution_index]
        )
        if (
            highest_resolution_norm_ref_error
            > omega_vs_reference_high_res_norm_rmse_threshold
        ):
            raise ValueError(
                'Normalized Omega-vs-reference RMS error at highest '
                f'resolution ({highest_resolution:g} km) is '
                f'{highest_resolution_norm_ref_error:.3e}, which exceeds '
                'omega_vs_reference_high_res_norm_rmse_threshold '
                f'({omega_vs_reference_high_res_norm_rmse_threshold:.3e}).'
            )

        if not (
            omega_vs_reference_convergence_rate_min
            <= ref_slope
            <= omega_vs_reference_convergence_rate_max
        ):
            raise ValueError(
                'Omega-vs-reference convergence slope is outside the '
                'allowed range: '
                f'{ref_slope:.3f} not in '
                f'[{omega_vs_reference_convergence_rate_min:.3f}, '
                f'{omega_vs_reference_convergence_rate_max:.3f}]'
            )


def _get_internal_edge(ds_init: xr.Dataset) -> tuple[int, tuple[int, int]]:
    """
    Determine the edge that connects the two valid cells in the two-column
    mesh.
    """
    if 'cellsOnEdge' not in ds_init:
        raise ValueError('cellsOnEdge is required in initial_state.nc')

    cells_on_edge = ds_init.cellsOnEdge.values.astype(int)
    if cells_on_edge.ndim != 2 or cells_on_edge.shape[1] != 2:
        raise ValueError('cellsOnEdge must have shape (nEdges, 2).')

    valid = np.logical_and(cells_on_edge[:, 0] > 0, cells_on_edge[:, 1] > 0)
    valid_edges = np.where(valid)[0]
    if len(valid_edges) != 1:
        raise ValueError(
            'Expected exactly one edge with two valid cells in the '
            f'two-column mesh, found {len(valid_edges)}.'
        )

    edge_index = int(valid_edges[0])
    # convert from 1-based MPAS indexing to 0-based indexing
    cell0 = int(cells_on_edge[edge_index, 0] - 1)
    cell1 = int(cells_on_edge[edge_index, 1] - 1)
    return edge_index, (cell0, cell1)


def _get_forward_z_tilde_edge_mid(
    ds_out: xr.Dataset,
    rho0: float,
    cell0: int,
    cell1: int,
) -> np.ndarray:
    """
    Compute edge-centered pseudo-height at layer midpoints from Omega output
    pressure.
    """
    pressure_mid = ds_out.PressureMid.isel(Time=0)
    pressure_edge_mid = 0.5 * (
        pressure_mid.isel(nCells=cell0) + pressure_mid.isel(nCells=cell1)
    )
    return (-pressure_edge_mid / (rho0 * Gravity)).values


def _sample_reference_without_interpolation(
    ref_z: np.ndarray,
    ref_values: np.ndarray,
    target_z: np.ndarray,
    ref_valid_mask: np.ndarray | None = None,
    target_valid_mask: np.ndarray | None = None,
    abs_tol: float = 1.0e-6,
    rel_tol: float = 1.0e-10,
) -> np.ndarray:
    """
    Sample reference values at target z-tilde values by exact matching within a
    strict tolerance, without interpolation.
    """
    ref_z = np.asarray(ref_z, dtype=float)
    ref_values = np.asarray(ref_values, dtype=float)
    target_z = np.asarray(target_z, dtype=float)
    if ref_valid_mask is not None:
        ref_valid_mask = np.asarray(ref_valid_mask, dtype=bool)
        if ref_valid_mask.shape != ref_z.shape:
            raise ValueError(
                'ref_valid_mask must have the same shape as ref_z.'
            )
    if target_valid_mask is not None:
        target_valid_mask = np.asarray(target_valid_mask, dtype=bool)
        if target_valid_mask.shape != target_z.shape:
            raise ValueError(
                'target_valid_mask must have the same shape as target_z.'
            )

    sampled = np.full_like(target_z, np.nan, dtype=float)
    valid_target = np.isfinite(target_z)
    if target_valid_mask is not None:
        valid_target = np.logical_and(valid_target, target_valid_mask)
    valid_ref = np.logical_and(np.isfinite(ref_z), np.isfinite(ref_values))
    if ref_valid_mask is not None:
        valid_ref = np.logical_and(valid_ref, ref_valid_mask)

    # The bottom valid forward layer hits bathymetry and should not be used
    # in the reference comparison.
    if np.any(valid_target):
        deepest = int(np.where(valid_target)[0][-1])
        valid_target[deepest] = False

    ref_z_valid = ref_z[valid_ref]
    ref_values_valid = ref_values[valid_ref]

    target_valid = target_z[valid_target]
    if len(target_valid) == 0:
        return sampled
    if len(ref_z_valid) == 0:
        raise ValueError(
            'No valid reference z-tilde values remain after applying '
            'ValidGradInterMask.'
        )

    dz = np.abs(ref_z_valid[:, np.newaxis] - target_valid[np.newaxis, :])
    indices = np.argmin(dz, axis=0)
    min_dz = dz[indices, np.arange(len(indices))]

    tol = np.maximum(abs_tol, rel_tol * np.maximum(1.0, np.abs(target_valid)))
    if np.any(min_dz > tol):
        max_mismatch = float(np.max(min_dz))
        raise ValueError(
            f'Reference z-tilde values do not match Omega z-tilde values '
            f'closely enough for subsampling without interpolation. max '
            f'|dz|={max_mismatch}'
        )

    sampled[valid_target] = ref_values_valid[indices]
    return sampled


def _check_vertical_match(
    z_ref: np.ndarray,
    z_test: np.ndarray,
    msg: str,
    valid_mask: np.ndarray | None = None,
    abs_tol: float = 1.0e-6,
    rel_tol: float = 1.0e-10,
) -> None:
    """
    Ensure two pseudo-height arrays match within strict tolerances.
    """
    z_ref = np.asarray(z_ref, dtype=float)
    z_test = np.asarray(z_test, dtype=float)
    if z_ref.shape != z_test.shape:
        raise ValueError(
            f'{msg}: shape mismatch {z_ref.shape} != {z_test.shape}'
        )

    if valid_mask is not None:
        valid_mask = np.asarray(valid_mask, dtype=bool)
        if valid_mask.shape != z_ref.shape:
            raise ValueError(
                f'{msg}: valid_mask shape mismatch '
                f'{valid_mask.shape} != {z_ref.shape}'
            )

    valid = np.logical_and(np.isfinite(z_ref), np.isfinite(z_test))
    if valid_mask is not None:
        valid = np.logical_and(valid, valid_mask)
    if not np.any(valid):
        raise ValueError(f'{msg}: no valid levels for comparison.')

    diff = np.abs(z_ref[valid] - z_test[valid])
    tol = np.maximum(abs_tol, rel_tol * np.maximum(1.0, np.abs(z_ref[valid])))
    if np.any(diff > tol):
        raise ValueError(
            f'{msg}: max |dz| = {float(np.max(diff))}, exceeds tolerance.'
        )


def _rms_error(values: np.ndarray) -> float:
    """
    Compute RMS over finite values.
    """
    values = np.asarray(values, dtype=float)
    valid = np.isfinite(values)
    if not np.any(valid):
        raise ValueError('No finite values available for RMS error.')
    return float(np.sqrt(np.mean(values[valid] ** 2)))


def _normalized_rms_error(
    values: np.ndarray,
    reference_values: np.ndarray,
    valid_mask: np.ndarray | None = None,
) -> float:
    """
    Compute normalized RMS error using max(abs(reference_values)).
    """
    values = np.asarray(values, dtype=float)
    reference_values = np.asarray(reference_values, dtype=float)
    if values.shape != reference_values.shape:
        raise ValueError(
            'values and reference_values must have the same shape for '
            'normalized RMS error.'
        )

    valid = np.logical_and(np.isfinite(values), np.isfinite(reference_values))
    if valid_mask is not None:
        valid_mask = np.asarray(valid_mask, dtype=bool)
        if valid_mask.shape != values.shape:
            raise ValueError(
                'valid_mask must have the same shape as values for '
                'normalized RMS error.'
            )
        valid = np.logical_and(valid, valid_mask)

    if not np.any(valid):
        raise ValueError(
            'No finite values available for normalized RMS error.'
        )

    max_abs_reference = float(np.max(np.abs(reference_values[valid])))
    if max_abs_reference <= 0.0:
        raise ValueError(
            'Cannot normalize RMS error because max(abs(reference_values)) '
            'is not positive.'
        )

    rms_error = _rms_error(values[valid])
    return rms_error / max_abs_reference


def _power_law_fit(
    x: np.ndarray,
    y: np.ndarray,
) -> tuple[np.ndarray, float, float]:
    """
    Fit y = 10**b * x**m in log10 space.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    valid = np.logical_and.reduce(
        (np.isfinite(x), np.isfinite(y), x > 0.0, y > 0.0)
    )

    if np.count_nonzero(valid) < 2:
        raise ValueError(
            'At least two positive finite points are required for fit.'
        )

    poly = np.polyfit(np.log10(x[valid]), np.log10(y[valid]), 1)
    slope = float(poly[0])
    intercept = float(poly[1])
    fit = x**slope * 10.0**intercept
    return fit, slope, intercept


def _write_dataset(
    filename: str,
    resolution_km: np.ndarray,
    rms_error: np.ndarray,
    y_name: str,
    y_units: str,
    fit: np.ndarray | None = None,
    slope: float | None = None,
    intercept: float | None = None,
) -> None:
    """
    Write data used in a convergence plot to netCDF.
    """
    nres = len(resolution_km)
    ds = xr.Dataset()
    ds['resolution_km'] = xr.DataArray(
        data=resolution_km,
        dims=['nResolutions'],
        attrs={'long_name': 'horizontal resolution', 'units': 'km'},
    )
    ds[y_name] = xr.DataArray(
        data=rms_error,
        dims=['nResolutions'],
        attrs={'long_name': y_name.replace('_', ' '), 'units': y_units},
    )
    if fit is not None:
        ds['power_law_fit'] = xr.DataArray(
            data=fit,
            dims=['nResolutions'],
            attrs={
                'long_name': 'power-law fit to rms error',
                'units': y_units,
            },
        )
    if slope is not None:
        ds.attrs['fit_slope'] = slope
    if intercept is not None:
        ds.attrs['fit_intercept_log10'] = intercept
    ds.attrs['nResolutions'] = nres
    ds.to_netcdf(filename)


def _plot_errors(
    resolution_km: np.ndarray,
    rms_error: np.ndarray,
    y_label: str,
    title: str,
    output: str,
    fit: np.ndarray | None = None,
    slope: float | None = None,
) -> None:
    """
    Plot RMS error vs. horizontal resolution with a power-law fit.
    """
    use_mplstyle()
    fig = plt.figure()
    ax = fig.add_subplot(111)

    if fit is not None:
        if slope is None:
            raise ValueError('slope must be provided when fit is provided.')
        ax.loglog(
            resolution_km,
            fit,
            'k',
            label=f'power-law fit (slope={slope:1.3f})',
        )
    ax.loglog(resolution_km, rms_error, 'o', label='RMS error')

    ax.set_xlabel('Horizontal resolution (km)')
    ax.set_ylabel(y_label)
    ax.set_title(title)
    ax.legend(loc='lower right')
    ax.invert_xaxis()
    fig.savefig(output, bbox_inches='tight', pad_inches=0.1)
    plt.close()
