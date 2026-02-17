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

        ds_ref = self.open_model_dataset('reference_solution.nc')
        if ds_ref.sizes.get('nCells', 0) <= 2:
            raise ValueError(
                'The reference solution requires at least 3 columns so that '
                'the central column is nCells=2.'
            )

        ref_z = ds_ref.ZTildeInter.isel(Time=0, nCells=2).values
        ref_hpga = ds_ref.HPGAInter.isel(Time=0).values

        ref_errors = []
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

            sampled_ref_hpga = _sample_reference_without_interpolation(
                ref_z=ref_z,
                ref_values=ref_hpga,
                target_z=z_tilde_forward,
            )

            ref_errors.append(_rms_error(hpga_forward - sampled_ref_hpga))

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
            )

            hpga_init = ds_init.HPGA.isel(Time=0).values
            py_errors.append(_rms_error(hpga_forward - hpga_init))

        resolution_array = np.asarray(horiz_resolutions, dtype=float)
        ref_error_array = np.asarray(ref_errors, dtype=float)
        py_error_array = np.asarray(py_errors, dtype=float)

        ref_fit, ref_slope, ref_intercept = _power_law_fit(
            x=resolution_array,
            y=ref_error_array,
        )
        py_fit, py_slope, py_intercept = _power_law_fit(
            x=resolution_array,
            y=py_error_array,
        )

        _write_dataset(
            filename='omega_vs_reference.nc',
            resolution_km=resolution_array,
            rms_error=ref_error_array,
            fit=ref_fit,
            slope=ref_slope,
            intercept=ref_intercept,
            y_name='rms_error_vs_reference',
        )
        _write_dataset(
            filename='omega_vs_python.nc',
            resolution_km=resolution_array,
            rms_error=py_error_array,
            fit=py_fit,
            slope=py_slope,
            intercept=py_intercept,
            y_name='rms_error_vs_python',
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
            fit=py_fit,
            slope=py_slope,
            y_label='RMS difference in HPGA (m s-2)',
            title='Omega (C++) vs Polaris (Python) HPGA Difference',
            output='omega_vs_python.png',
        )

        logger.info(f'Omega-vs-reference convergence slope: {ref_slope:1.3f}')
        logger.info(f'Omega-vs-Python convergence slope: {py_slope:1.3f}')


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

    sampled = np.full_like(target_z, np.nan, dtype=float)
    valid_target = np.isfinite(target_z)
    valid_ref = np.logical_and(np.isfinite(ref_z), np.isfinite(ref_values))

    ref_z_valid = ref_z[valid_ref]
    ref_values_valid = ref_values[valid_ref]

    target_valid = target_z[valid_target]
    if len(target_valid) == 0:
        return sampled

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

    valid = np.logical_and(np.isfinite(z_ref), np.isfinite(z_test))
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
    fit: np.ndarray,
    slope: float,
    intercept: float,
    y_name: str,
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
        attrs={'long_name': y_name.replace('_', ' '), 'units': 'm s-2'},
    )
    ds['power_law_fit'] = xr.DataArray(
        data=fit,
        dims=['nResolutions'],
        attrs={'long_name': 'power-law fit to rms error', 'units': 'm s-2'},
    )
    ds.attrs['fit_slope'] = slope
    ds.attrs['fit_intercept_log10'] = intercept
    ds.attrs['nResolutions'] = nres
    ds.to_netcdf(filename)


def _plot_errors(
    resolution_km: np.ndarray,
    rms_error: np.ndarray,
    fit: np.ndarray,
    slope: float,
    y_label: str,
    title: str,
    output: str,
) -> None:
    """
    Plot RMS error vs. horizontal resolution with a power-law fit.
    """
    use_mplstyle()
    fig = plt.figure()
    ax = fig.add_subplot(111)

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
