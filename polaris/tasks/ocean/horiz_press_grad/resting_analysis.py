import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

from polaris.ocean.model import OceanIOStep
from polaris.tasks.ocean.horiz_press_grad.metrics import (
    format_value_error_pairs,
    format_value_list,
    get_internal_edge,
    power_law_fit,
    rms,
)
from polaris.viz import use_mplstyle


class RestingAnalysis(OceanIOStep):
    """
    A step for analyzing the two-column HPGA in an exact resting state, where
    the true HPGA is identically zero and no reference solution is needed.

    Unlike :py:class:`~polaris.tasks.ocean.horiz_press_grad.analysis.Analysis`,
    which measures convergence toward a quasi-analytic reference, this step
    measures the absolute HPGA (which is entirely error) as a function of a
    swept coordinate or bathymetric tilt, and fits the exponent ``q`` in
    ``|HPGA| ~ tilt**q``.

    It also includes the deepest layer valid in both columns bounding the
    edge, which ``Analysis`` deliberately drops.  That layer is the bottom
    partial cell, and in a p-star column with a stepped sea floor it carries
    the entire signal.

    Attributes
    ----------
    dependencies_dict : dict
        A dictionary of dependent steps:

        init : dict
            Mapping from ``(horiz_res, vert_res, tilt)`` to ``Init`` step

        forward : dict
            Mapping from ``(horiz_res, vert_res, tilt)`` to ``Forward`` step

    sweep_keys : list of tuple
        The ``(horiz_res, vert_res, tilt)`` triples in the sweep, in the order
        they are analyzed.
    """

    def __init__(self, component, indir, dependencies, sweep_keys):
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

        sweep_keys : list of tuple
            The ``(horiz_res, vert_res, tilt)`` triples in the sweep
        """
        super().__init__(component=component, name='analysis', indir=indir)

        self.dependencies_dict = dependencies
        self.sweep_keys = list(sweep_keys)

        self.add_output_file('resting_state.png')
        self.add_output_file('resting_state.nc')

    def setup(self):
        """
        Add inputs from init and forward steps
        """
        super().setup()

        init_steps = self.dependencies_dict['init']
        forward_steps = self.dependencies_dict['forward']
        for key in self.sweep_keys:
            init = init_steps[key]
            forward = forward_steps[key]
            suffix = sweep_suffix(*key)
            self.add_input_file(
                filename=f'init_{suffix}.nc',
                work_dir_target=f'{init.path}/init.nc',
            )
            self.add_input_file(
                filename=f'output_{suffix}.nc',
                work_dir_target=f'{forward.path}/output.nc',
            )
            self.add_input_file(
                filename=f'culled_mesh_{suffix}.nc',
                work_dir_target=f'{init.path}/culled_mesh.nc',
            )
            self.add_vert_coord_input_file(
                filename=f'vert_coord_{suffix}.nc',
                work_dir_target=f'{init.path}/vert_coord.nc',
            )

    def run(self):
        """
        Run this step of the test case
        """
        plt.switch_backend('Agg')
        logger = self.logger
        config = self.config

        section = config['horiz_press_grad']
        tilt_option = section.get('tilt_option')
        tilt_fit = section.getboolean('tilt_fit')
        tilt_fit_max = section.getfloat('tilt_fit_max')
        sensitivity_min_rms = section.getfloat(
            'resting_state_sensitivity_min_rms'
        )
        max_bathy_error = section.getfloat('resting_state_max_bathy_error')
        omega_vs_polaris_rms_threshold = section.getfloat(
            'omega_vs_polaris_rms_threshold'
        )
        max_rms_text = section.get('resting_state_max_rms').strip().lower()
        max_rms = None if max_rms_text == 'none' else float(max_rms_text)

        omega_rms = []
        polaris_rms = []
        diff_rms = []
        bathy_error = []
        n_layers = []

        for key in self.sweep_keys:
            suffix = sweep_suffix(*key)
            ds_init = self.open_model_dataset(f'init_{suffix}.nc', config)
            ds_mesh = self.open_model_dataset(
                f'culled_mesh_{suffix}.nc', config
            )
            ds_out = self.open_model_dataset(
                f'output_{suffix}.nc', config, decode_times=False
            )
            ds_vc = self.open_vert_coord_dataset(
                ds_init, vert_coord_filename=f'vert_coord_{suffix}.nc'
            )

            edge_index, (cell0, cell1) = get_internal_edge(ds_mesh)

            # maxLevelCell is 1-based; the deepest layer valid in BOTH columns
            # has 0-based index min(maxLevelCell) - 1.  It is kept: it is the
            # bottom partial cell, where the resting-state error concentrates.
            max_level_cells = ds_vc.maxLevelCell.isel(
                nCells=[cell0, cell1]
            ).values.astype(int)
            n_valid = int(np.min(max_level_cells))
            if n_valid < 1:
                raise ValueError(
                    f'Invalid maxLevelCell values {max_level_cells} for '
                    f'sweep point {suffix}.'
                )
            n_layers.append(n_valid)

            hpga_omega = ds_out.NormalVelocityTend.isel(
                Time=0, nEdges=edge_index
            ).values[:n_valid]
            hpga_polaris = ds_init.HPGA.isel(Time=0).values[:n_valid]

            # the true HPGA is identically zero, so the model's HPGA is the
            # error and no reference solution is involved
            omega_rms.append(rms(hpga_omega))
            polaris_rms.append(rms(hpga_polaris))
            diff_rms.append(rms(hpga_omega - hpga_polaris))

            # The p-star column is anchored at the prescribed sea surface,
            # so ssh is exact by construction and cannot reveal a problem.
            # Partial-cell snapping instead moves the sea floor, which
            # silently changes the geometry being swept -- see
            # _check_bathymetry.
            bathy_error.append(
                float(
                    np.max(
                        np.abs(
                            ds_vc.bottomDepth.values.ravel()
                            - ds_init.bottomDepthRequested.values.ravel()
                        )
                    )
                )
            )

        tilts = np.array([key[2] for key in self.sweep_keys], dtype=float)
        omega_rms = np.asarray(omega_rms, dtype=float)
        polaris_rms = np.asarray(polaris_rms, dtype=float)
        diff_rms = np.asarray(diff_rms, dtype=float)
        bathy_error = np.asarray(bathy_error, dtype=float)

        groups = _group_by_resolution(self.sweep_keys)
        exponents = _fit_exponents(
            groups=groups,
            tilts=tilts,
            values=omega_rms,
            tilt_fit=tilt_fit,
            tilt_fit_max=tilt_fit_max,
        )

        _write_resting_dataset(
            filename='resting_state.nc',
            sweep_keys=self.sweep_keys,
            omega_rms=omega_rms,
            polaris_rms=polaris_rms,
            diff_rms=diff_rms,
            bathy_error=bathy_error,
            n_layers=np.asarray(n_layers, dtype=int),
            exponents=exponents,
            tilt_option=tilt_option,
        )
        _plot_resting(
            output='resting_state.png',
            groups=groups,
            tilts=tilts,
            values=omega_rms,
            exponents=exponents,
            tilt_option=tilt_option,
            sensitivity_min_rms=sensitivity_min_rms,
        )

        logger.info(f'Resting-state sweep over {tilt_option} (m/km):')
        for label, indices in groups.items():
            logger.info(
                f'  {label}: '
                f'{format_value_error_pairs(tilts[indices], omega_rms[indices], units="m/km")}'  # noqa: E501
            )
            if label in exponents:
                logger.info(
                    f'  {label}: fitted tilt exponent q = '
                    f'{exponents[label]:.3f} over tilts '
                    f'{format_value_list(tilts[indices][tilts[indices] <= tilt_fit_max])}'  # noqa: E501
                )

        self._check_bathymetry(bathy_error, max_bathy_error)
        self._check_omega_vs_polaris(diff_rms, omega_vs_polaris_rms_threshold)
        self._check_sensitivity(omega_rms, sensitivity_min_rms)
        self._check_max_rms(omega_rms, max_rms)

    def _check_bathymetry(self, bathy_error, max_bathy_error):
        """
        Fail if the sea floor is not where the configuration asked for it.

        The resting-state property survives a moved sea floor -- the state is
        still exactly at rest -- but the swept parameter stops meaning what it
        says, because the geometry actually tested is no longer the configured
        one.  Partial-cell snapping moves the sea floor to the nearest
        representable depth, and at some gradients that collapses the step
        between the two columns to nothing, so the test would report a
        near-zero error for a configuration nominally carrying a large step.
        """
        failing = bathy_error > max_bathy_error
        if not np.any(failing):
            return
        raise ValueError(
            'The sea floor is not at the requested depth, so the swept tilt '
            'is not the geometry actually being tested. This means the '
            'vertical-grid construction moved the bathymetry -- normally '
            'partial-cell snapping to the nearest representable depth. Set '
            '"partial_cell_type = None" for resting-state variants. Max '
            f'|bottomDepth - requested| = {float(np.max(bathy_error)):.3e} m '
            f'exceeds resting_state_max_bathy_error={max_bathy_error:.3e} m '
            f'at: {self._failing_text(failing, bathy_error)}'
        )

    def _check_omega_vs_polaris(self, diff_rms, threshold):
        """
        Fail if Omega and Polaris disagree about the same discrete scheme.
        """
        failing = diff_rms > threshold
        if not np.any(failing):
            return
        raise ValueError(
            'Omega-vs-Polaris RMS difference exceeds '
            f'omega_vs_polaris_rms_threshold={threshold:.3e} at: '
            f'{self._failing_text(failing, diff_rms)}'
        )

    def _check_sensitivity(self, omega_rms, sensitivity_min_rms):
        """
        Fail if the sweep never drives the scheme hard enough to be
        informative about the failure mode it is meant to probe.
        """
        largest = float(np.max(omega_rms))
        if largest >= sensitivity_min_rms:
            return
        raise ValueError(
            'The resting-state sweep is not severe enough to exercise the '
            'pressure-gradient error it exists to measure: the largest RMS '
            f'HPGA anywhere in the sweep is {largest:.3e} m s-2, below '
            f'resting_state_sensitivity_min_rms={sensitivity_min_rms:.3e} '
            'm s-2. The sweep must be made more severe (coarser layers or '
            'larger tilt) before any conclusion is drawn from it.'
        )

    def _check_max_rms(self, omega_rms, max_rms):
        """
        Fail if the scheme exceeds the consistency threshold, when one is set.
        """
        if max_rms is None:
            return
        failing = omega_rms > max_rms
        if not np.any(failing):
            return
        raise ValueError(
            'RMS HPGA in the resting state exceeds '
            f'resting_state_max_rms={max_rms:.3e} m s-2 at: '
            f'{self._failing_text(failing, omega_rms)}'
        )

    def _failing_text(self, failing, values):
        """
        Format the sweep points where a check failed.
        """
        return ', '.join(
            f'{sweep_suffix(*self.sweep_keys[index])}: {values[index]:.3e}'
            for index in np.where(failing)[0]
        )


def sweep_suffix(horiz_res, vert_res, tilt):
    """
    Build a filename- and directory-safe suffix for one sweep point.

    Parameters
    ----------
    horiz_res : float
        The horizontal resolution in km

    vert_res : float
        The vertical resolution in m

    tilt : float
        The swept tilt in m/km

    Returns
    -------
    str
        A suffix such as ``4km_256m_tilt0p5``
    """
    return (
        f'{_number_to_string(horiz_res)}km_'
        f'{_number_to_string(vert_res)}m_'
        f'tilt{_number_to_string(tilt)}'
    )


def _number_to_string(value):
    """
    Format a number compactly, with ``p`` standing in for the decimal point.
    """
    return f'{float(value):g}'.replace('.', 'p').replace('-', 'm')


def _group_by_resolution(sweep_keys):
    """
    Group sweep indices by their ``(horiz_res, vert_res)`` pair, preserving
    the order in which the pairs first appear.
    """
    groups: dict[str, list[int]] = {}
    for index, (horiz_res, vert_res, _) in enumerate(sweep_keys):
        label = f'{horiz_res:g} km, {vert_res:g} m'
        groups.setdefault(label, []).append(index)
    return {label: np.asarray(indices) for label, indices in groups.items()}


def _fit_exponents(groups, tilts, values, tilt_fit, tilt_fit_max):
    """
    Fit the tilt exponent within each resolution group, skipping groups with
    too few usable points rather than raising.
    """
    exponents: dict[str, float] = {}
    if not tilt_fit:
        return exponents
    for label, indices in groups.items():
        group_tilts = tilts[indices]
        group_values = values[indices]
        fit_mask = group_tilts <= tilt_fit_max
        usable = np.logical_and.reduce(
            (fit_mask, group_tilts > 0.0, group_values > 0.0)
        )
        if np.count_nonzero(usable) < 2:
            continue
        _, slope, _ = power_law_fit(
            x=group_tilts, y=group_values, fit_mask=fit_mask
        )
        exponents[label] = slope
    return exponents


def _write_resting_dataset(
    filename,
    sweep_keys,
    omega_rms,
    polaris_rms,
    diff_rms,
    bathy_error,
    n_layers,
    exponents,
    tilt_option,
):
    """
    Write the resting-state sweep results to netCDF.
    """
    ds = xr.Dataset()
    ds['horiz_resolution'] = xr.DataArray(
        data=np.array([key[0] for key in sweep_keys], dtype=float),
        dims=['nSweep'],
        attrs={'long_name': 'horizontal resolution', 'units': 'km'},
    )
    ds['vert_resolution'] = xr.DataArray(
        data=np.array([key[1] for key in sweep_keys], dtype=float),
        dims=['nSweep'],
        attrs={'long_name': 'vertical resolution', 'units': 'm'},
    )
    ds['tilt'] = xr.DataArray(
        data=np.array([key[2] for key in sweep_keys], dtype=float),
        dims=['nSweep'],
        attrs={'long_name': f'swept {tilt_option}', 'units': 'm km-1'},
    )
    ds['rms_hpga_omega'] = xr.DataArray(
        data=omega_rms,
        dims=['nSweep'],
        attrs={
            'long_name': 'RMS HPGA from Omega (the error; truth is zero)',
            'units': 'm s-2',
        },
    )
    ds['rms_hpga_polaris'] = xr.DataArray(
        data=polaris_rms,
        dims=['nSweep'],
        attrs={
            'long_name': 'RMS HPGA from the Polaris initial condition',
            'units': 'm s-2',
        },
    )
    ds['rms_omega_vs_polaris'] = xr.DataArray(
        data=diff_rms,
        dims=['nSweep'],
        attrs={
            'long_name': 'RMS difference between Omega and Polaris HPGA',
            'units': 'm s-2',
        },
    )
    ds['bathymetry_error'] = xr.DataArray(
        data=bathy_error,
        dims=['nSweep'],
        attrs={
            'long_name': 'max |bottomDepth - requested| over the two columns',
            'units': 'm',
        },
    )
    ds['n_layers'] = xr.DataArray(
        data=n_layers,
        dims=['nSweep'],
        attrs={
            'long_name': 'number of layers valid in both columns',
            'units': '1',
        },
    )
    ds.attrs['tilt_option'] = tilt_option
    for label, slope in exponents.items():
        ds.attrs[f'tilt_exponent ({label})'] = slope
    ds.to_netcdf(filename)


def _plot_resting(
    output,
    groups,
    tilts,
    values,
    exponents,
    tilt_option,
    sensitivity_min_rms,
):
    """
    Plot RMS HPGA against the swept tilt, one series per resolution pair.
    """
    use_mplstyle()
    fig = plt.figure()
    ax = fig.add_subplot(111)

    for label, indices in groups.items():
        legend = label
        if label in exponents:
            legend = f'{label} (q={exponents[label]:.2f})'
        ax.loglog(tilts[indices], values[indices], 'o-', label=legend)

    ax.axhline(
        sensitivity_min_rms,
        color='k',
        linestyle='--',
        label=f'sensitivity gate ({sensitivity_min_rms:g})',
    )
    ax.set_xlabel(f'{tilt_option} (m km-1)')
    ax.set_ylabel('RMS HPGA in a resting state (m s-2)')
    ax.set_title('Resting-State HPGA vs Tilt (true HPGA is zero)')
    ax.legend(loc='best')
    fig.savefig(output, bbox_inches='tight', pad_inches=0.1)
    plt.close()
