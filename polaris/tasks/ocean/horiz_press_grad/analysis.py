import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

from polaris.ocean.model import OceanIOStep
from polaris.ocean.vertical.ztilde import Gravity, RhoSw
from polaris.tasks.ocean.horiz_press_grad.forward import SCHEME_HPGA
from polaris.tasks.ocean.horiz_press_grad.metrics import (
    format_value_error_pairs,
    format_value_list,
    get_internal_edge,
    power_law_fit,
    rms,
    write_metric_dataset,
)
from polaris.tasks.ocean.horiz_press_grad.reference import ReferenceColumn
from polaris.viz import use_mplstyle


class Analysis(OceanIOStep):
    """
    A step for analyzing two-column HPGA errors versus a reference solution
    and versus the Python-computed initial-state solution.

    Attributes
    ----------
    dependencies_dict : dict
        A dictionary of dependent steps:

        init : dict
            Mapping from horizontal resolution (km) to ``Init`` step

        forward : dict
            Mapping from ``(horizontal resolution, scheme)`` to ``Forward``
            step

    schemes : list of str
        The pressure-gradient schemes being compared
    """

    def __init__(self, component, indir, dependencies, schemes):
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

        schemes : list of str
            The pressure-gradient schemes being compared
        """
        super().__init__(component=component, name='analysis', indir=indir)

        self.dependencies_dict = dependencies
        self.schemes = list(schemes)

        self.add_output_file('omega_vs_reference.png')
        self.add_output_file('omega_vs_reference.nc')
        self.add_output_file('omega_vs_python.png')
        self.add_output_file('omega_vs_python.nc')

    def setup(self):
        """
        Add inputs from init and forward steps
        """
        super().setup()

        section = self.config['horiz_press_grad']
        horiz_resolutions = section.getexpression('horiz_resolutions')
        assert horiz_resolutions is not None

        init_steps = self.dependencies_dict['init']
        forward_steps = self.dependencies_dict['forward']
        for resolution in horiz_resolutions:
            init = init_steps[resolution]
            self.add_input_file(
                filename=f'init_r{resolution:02g}.nc',
                work_dir_target=f'{init.path}/init.nc',
            )
            self.add_input_file(
                filename=f'culled_mesh_r{resolution:02g}.nc',
                work_dir_target=f'{init.path}/culled_mesh.nc',
            )
            self.add_vert_coord_input_file(
                filename=f'vert_coord_r{resolution:02g}.nc',
                work_dir_target=f'{init.path}/vert_coord.nc',
            )
            for scheme in self.schemes:
                forward = forward_steps[resolution, scheme]
                self.add_input_file(
                    filename=f'output_r{resolution:02g}_{scheme}.nc',
                    work_dir_target=f'{forward.path}/output.nc',
                )

    def run(self):
        """
        Run this step of the test case
        """
        plt.switch_backend('Agg')
        logger = self.logger
        config = self.config

        section = config['horiz_press_grad']
        horiz_resolutions = section.getexpression('horiz_resolutions')
        assert horiz_resolutions is not None, (
            'The "horiz_resolutions" configuration option must be set in '
            'the "horiz_press_grad" section.'
        )
        # bands are per scheme: on ztilde_gradient the centered scheme is first
        # order and the finite-volume scheme second, so one band cannot hold
        # both
        rate_min: dict[str, float] = {}
        rate_max: dict[str, float] = {}
        for scheme in self.schemes:
            for bound, target in (('min', rate_min), ('max', rate_max)):
                option = (
                    f'omega_vs_reference_convergence_rate_{bound}_{scheme}'
                )
                value = section.getfloat(option)
                assert value is not None, (
                    f'The "{option}" configuration option must be set in the '
                    '"horiz_press_grad" section.'
                )
                target[scheme] = value

        accuracy_ratio_min = section.getfloat(
            'omega_vs_reference_accuracy_ratio_min'
        )
        assert accuracy_ratio_min is not None, (
            'The "omega_vs_reference_accuracy_ratio_min" configuration '
            'option must be set in the "horiz_press_grad" section.'
        )
        omega_vs_reference_convergence_fit_max_resolution = section.getfloat(
            'omega_vs_reference_convergence_fit_max_resolution'
        )
        assert omega_vs_reference_convergence_fit_max_resolution is not None, (
            'The "omega_vs_reference_convergence_fit_max_resolution" '
            'configuration option must be set in the "horiz_press_grad" '
            'section.'
        )
        omega_vs_reference_high_res_rms_threshold = section.getfloat(
            'omega_vs_reference_high_res_rms_threshold'
        )
        assert omega_vs_reference_high_res_rms_threshold is not None, (
            'The "omega_vs_reference_high_res_rms_threshold" '
            'configuration option must be set in the "horiz_press_grad" '
            'section.'
        )
        omega_vs_polaris_rms_threshold = section.getfloat(
            'omega_vs_polaris_rms_threshold'
        )
        assert omega_vs_polaris_rms_threshold is not None, (
            'The "omega_vs_polaris_rms_threshold" configuration option '
            'must be set in the "horiz_press_grad" section.'
        )

        ref_errors: dict[str, list[float]] = {
            scheme: [] for scheme in self.schemes
        }
        py_errors: dict[str, list[float]] = {
            scheme: [] for scheme in self.schemes
        }

        for resolution in horiz_resolutions:
            ds_init = self.open_model_dataset(
                f'init_r{resolution:02g}.nc', self.config
            )
            ds_mesh = self.open_model_dataset(
                f'culled_mesh_r{resolution:02g}.nc', self.config
            )

            edge_index, cells_on_edge = get_internal_edge(ds_mesh)
            cell0, cell1 = cells_on_edge

            # maxLevelCell is one-based (Fortran indexing), convert to
            # zero-based and use the shallowest valid bottom among the two
            # cells that bound the internal edge.
            ds_vc = self.open_vert_coord_dataset(
                ds_init,
                vert_coord_filename=f'vert_coord_r{resolution:02g}.nc',
            )
            max_level_cells = ds_vc.maxLevelCell.isel(
                nCells=[cell0, cell1]
            ).values.astype(int)
            max_level_index = int(np.min(max_level_cells) - 1)
            if max_level_index < 0:
                raise ValueError(
                    f'Invalid maxLevelCell values {max_level_cells} at '
                    f'resolution {resolution:g} km.'
                )

            # Build reference evaluator: x_sign aligns config +x with the
            # edge normal (from cell0 toward cell1).  The reference is a
            # property of the state, not of the scheme, so it is built once
            # and both schemes are measured against the same one.
            x_sign = float(
                np.sign(
                    ds_mesh.xCell.values[cell1] - ds_mesh.xCell.values[cell0]
                )
            )
            ref = ReferenceColumn(config, x_sign=x_sign)

            # Edge interface z̃: average of the two bounding cells
            z_tilde_inter_edge = 0.5 * (
                ds_init.ZTildeInterface.isel(Time=0, nCells=cell0).values
                + ds_init.ZTildeInterface.isel(Time=0, nCells=cell1).values
            )

            # All layers valid in both columns (0..max_level_index), bounded
            # by interfaces 0..max_level_index+1.  The deepest of these abuts
            # the bathymetry and is deliberately kept: it is the bottom
            # partial cell, where pressure-gradient error concentrates.  It
            # was excluded when the reference was a cross-column
            # finite-difference stencil that could not be formed there; the
            # reference is now a single analytic column at the edge (see
            # ReferenceColumn), valid to the seafloor, so the exclusion no
            # longer has a basis.
            z_tilde_inter_for_ref = z_tilde_inter_edge[: max_level_index + 2]
            ref_layer_mean = ref.layer_mean_hpga(z_tilde_inter_for_ref)

            z_tilde_init = (
                0.5
                * (
                    ds_init.ZTildeMid.isel(Time=0, nCells=cell0)
                    + ds_init.ZTildeMid.isel(Time=0, nCells=cell1)
                ).values
            )

            for scheme in self.schemes:
                ds_out = self.open_model_dataset(
                    f'output_r{resolution:02g}_{scheme}.nc',
                    self.config,
                    decode_times=False,
                )

                z_tilde_forward = _get_forward_z_tilde_edge_mid(
                    ds_out=ds_out,
                    cell0=cell0,
                    cell1=cell1,
                )
                hpga_forward = ds_out.NormalVelocityTend.isel(
                    Time=0, nEdges=edge_index
                ).values

                forward_valid_mask = np.zeros_like(hpga_forward, dtype=bool)
                forward_valid_mask[: max_level_index + 1] = True

                hpga_ref_diff = (
                    hpga_forward[: max_level_index + 1] - ref_layer_mean
                )
                ref_errors[scheme].append(rms(hpga_ref_diff))

                _check_vertical_match(
                    z_ref=z_tilde_init,
                    z_test=z_tilde_forward,
                    msg=(
                        'ZTilde mismatch between Python init and Omega '
                        f'forward at resolution {resolution:g} km, '
                        f'{scheme} scheme'
                    ),
                    valid_mask=forward_valid_mask,
                )

                # each scheme is compared against its OWN Polaris counterpart;
                # comparing Omega's finite-volume output against the centered
                # HPGA would measure the difference between two schemes and
                # report it as an implementation disagreement
                hpga_init = ds_init[SCHEME_HPGA[scheme]].isel(Time=0).values
                hpga_diff = hpga_forward - hpga_init
                py_errors[scheme].append(rms(hpga_diff[forward_valid_mask]))

        resolution_array = np.asarray(horiz_resolutions, dtype=float)
        ref_error_arrays = {
            scheme: np.asarray(values, dtype=float)
            for scheme, values in ref_errors.items()
        }
        py_error_arrays = {
            scheme: np.asarray(values, dtype=float)
            for scheme, values in py_errors.items()
        }

        fit_mask = (
            resolution_array
            <= omega_vs_reference_convergence_fit_max_resolution
        )

        ref_fits = {}
        ref_slopes = {}
        ref_intercepts = {}
        for scheme, values in ref_error_arrays.items():
            fit, slope, intercept = power_law_fit(
                x=resolution_array, y=values, fit_mask=fit_mask
            )
            ref_fits[scheme] = fit
            ref_slopes[scheme] = slope
            ref_intercepts[scheme] = intercept

        write_metric_dataset(
            filename='omega_vs_reference.nc',
            resolution_km=resolution_array,
            rms_error=ref_error_arrays,
            fit=ref_fits,
            slope=ref_slopes,
            intercept=ref_intercepts,
            y_name='rms_error_vs_reference',
            y_units='m s-2',
        )
        write_metric_dataset(
            filename='omega_vs_python.nc',
            resolution_km=resolution_array,
            rms_error=py_error_arrays,
            y_name='rms_error_vs_python',
            y_units='m s-2',
        )

        _plot_errors(
            resolution_km=resolution_array,
            rms_error=ref_error_arrays,
            fit=ref_fits,
            slope=ref_slopes,
            y_label='RMS error in HPGA (m s-2)',
            title='Omega HPGA Error vs Reference Solution',
            output='omega_vs_reference.png',
        )
        _plot_errors(
            resolution_km=resolution_array,
            rms_error=py_error_arrays,
            y_label='RMS difference in HPGA (m s-2)',
            title='Omega vs Polaris HPGA RMS Difference',
            output='omega_vs_python.png',
        )

        logger.info(
            'Omega-vs-reference fit uses resolutions (km): '
            f'{format_value_list(resolution_array[fit_mask])}'
        )
        for scheme in self.schemes:
            logger.info(
                f'{scheme}: convergence slope {ref_slopes[scheme]:1.3f}; '
                'RMS vs reference '
                + format_value_error_pairs(
                    resolution_array, ref_error_arrays[scheme]
                )
            )
            logger.info(
                f'{scheme}: Omega-vs-Polaris RMS differences '
                + format_value_error_pairs(
                    resolution_array, py_error_arrays[scheme]
                )
            )

        highest_resolution_index = int(np.argmin(resolution_array))
        highest_resolution = float(resolution_array[highest_resolution_index])

        for scheme in self.schemes:
            py_error_array = py_error_arrays[scheme]
            failing_polaris = py_error_array > omega_vs_polaris_rms_threshold
            if np.any(failing_polaris):
                failing_text = ', '.join(
                    [
                        f'{resolution_array[index]:g} km: '
                        f'{py_error_array[index]:.3e}'
                        for index in np.where(failing_polaris)[0]
                    ]
                )
                raise ValueError(
                    f'{scheme}: Omega-vs-Polaris RMS difference exceeds '
                    f'omega_vs_polaris_rms_threshold='
                    f'{omega_vs_polaris_rms_threshold:.3e} at: {failing_text}'
                )

            highest_resolution_ref_error = float(
                ref_error_arrays[scheme][highest_resolution_index]
            )
            if (
                highest_resolution_ref_error
                > omega_vs_reference_high_res_rms_threshold
            ):
                raise ValueError(
                    f'{scheme}: Omega-vs-reference RMS error at highest '
                    f'resolution ({highest_resolution:g} km) is '
                    f'{highest_resolution_ref_error:.3e}, which exceeds '
                    'omega_vs_reference_high_res_rms_threshold '
                    f'({omega_vs_reference_high_res_rms_threshold:.3e}).'
                )

            ref_slope = ref_slopes[scheme]
            if not (rate_min[scheme] <= ref_slope <= rate_max[scheme]):
                raise ValueError(
                    f'{scheme}: Omega-vs-reference convergence slope is '
                    'outside the allowed range: '
                    f'{ref_slope:.3f} not in '
                    f'[{rate_min[scheme]:.3f}, {rate_max[scheme]:.3f}]'
                )

        # Accuracy gate, at the coarsest resolution.  Deliberately a ratio of
        # errors rather than a comparison of convergence orders: on a smooth
        # profile the two schemes converge at the same rate, so an
        # order-based gate would fail where nothing is wrong.  The coarse end
        # is used because that is where the advantage is smallest on the one
        # variant whose schemes differ in order.
        if 'centered' in ref_error_arrays and (
            'finite_volume' in ref_error_arrays
        ):
            coarsest = int(np.argmax(resolution_array))
            centered_error = float(ref_error_arrays['centered'][coarsest])
            finite_error = float(ref_error_arrays['finite_volume'][coarsest])
            ratio = centered_error / finite_error
            logger.info(
                f'centered / finite_volume RMS at '
                f'{resolution_array[coarsest]:g} km: {ratio:.2f}x'
            )
            if ratio < accuracy_ratio_min:
                raise ValueError(
                    'The finite-volume scheme is not as accurate as '
                    'omega_vs_reference_accuracy_ratio_min requires at the '
                    f'coarsest resolution ({resolution_array[coarsest]:g} '
                    f'km): centered {centered_error:.3e} over finite_volume '
                    f'{finite_error:.3e} is {ratio:.3f}, below '
                    f'{accuracy_ratio_min:.3f}'
                )


def _get_forward_z_tilde_edge_mid(
    ds_out: xr.Dataset,
    cell0: int,
    cell1: int,
) -> np.ndarray:
    """
    Compute edge-centered pseudo-height at layer midpoints from Omega output
    pressure.
    """
    pressure_mid = ds_out.pressure.isel(Time=0)
    pressure_edge_mid = 0.5 * (
        pressure_mid.isel(nCells=cell0) + pressure_mid.isel(nCells=cell1)
    )
    return (-pressure_edge_mid / (RhoSw * Gravity)).values


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


def _plot_errors(
    resolution_km: np.ndarray,
    rms_error: dict[str, np.ndarray],
    y_label: str,
    title: str,
    output: str,
    fit: dict[str, np.ndarray] | None = None,
    slope: dict[str, float] | None = None,
) -> None:
    """
    Plot RMS error vs. horizontal resolution, one series per scheme, with a
    power-law fit per scheme.
    """
    use_mplstyle()
    fig = plt.figure()
    ax = fig.add_subplot(111)

    for index, (scheme, values) in enumerate(rms_error.items()):
        color = f'C{index}'
        if fit is not None and scheme in fit:
            if slope is None or scheme not in slope:
                raise ValueError(
                    'slope must be provided for every scheme in fit.'
                )
            ax.loglog(
                resolution_km,
                fit[scheme],
                '-',
                color=color,
                label=f'{scheme} fit (slope={slope[scheme]:1.3f})',
            )
        ax.loglog(resolution_km, values, 'o', color=color, label=scheme)

    ax.set_xlabel('Horizontal resolution (km)')
    ax.set_ylabel(y_label)
    ax.set_title(title)
    ax.legend(loc='lower right')
    ax.invert_xaxis()
    fig.savefig(output, bbox_inches='tight', pad_inches=0.1)
    plt.close()
