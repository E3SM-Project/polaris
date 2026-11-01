import matplotlib.pyplot as plt
import numpy as np

from polaris.ocean.model import OceanIOStep
from polaris.tasks.ocean.mixed_layer_eddies.diagnostics import (
    compute_fk11_stream_function,
    compute_model_stream_function,
    get_consistent_edges,
    get_frontal_cell_mask,
)
from polaris.viz import mplstyle_context

# the parameterization settings that are verified
VERIFIED_SETTINGS = ('on',)


class Verify(OceanIOStep):
    """
    A step for verifying that the coarse runs' submesoscale eddy
    parameterization produces the stream function its formula gives for the
    runs' own state

    Attributes
    ----------
    runs : list of tuple
        The resolution directory and parameterization setting of each run
    """

    def __init__(self, component, indir, coarse_steps):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        indir : str
            The directory the step is in, to which ``name`` will be appended

        coarse_steps : dict of dict of polaris.Step
            The shared steps at each coarse resolution, keyed by the
            resolution's directory name and then the step name
        """
        super().__init__(component=component, name='verify', indir=indir)
        self.runs = []
        for resdir, steps in coarse_steps.items():
            init = steps['init']
            self.add_input_file(
                filename=f'mesh_{resdir}.nc',
                work_dir_target=f'{init.path}/culled_mesh.nc',
            )
            for mle in VERIFIED_SETTINGS:
                forward = steps[f'forward_{mle}']
                self.add_input_file(
                    filename=f'output_{resdir}_{mle}.nc',
                    work_dir_target=f'{forward.path}/output.nc',
                )
                self.runs.append((resdir, mle))
        self.add_output_file(filename='verification.png')

    def run(self):
        """
        Run this step of the task
        """
        config = self.config
        logger = self.logger
        section = config['mixed_layer_eddies_analysis']
        frontal_zone_fraction = section.getfloat('frontal_zone_fraction')
        min_fraction = section.getfloat('verify_min_consistent_fraction')
        verify_day = section.getint('verify_day')
        model = config.get('ocean', 'model')

        results = []
        for resdir, mle in self.runs:
            tolerance = section.getfloat(f'verify_tolerance_{resdir}')
            if not np.isfinite(tolerance) or tolerance <= 0.0:
                raise ValueError(
                    f'{resdir}: verification tolerance must be finite '
                    'and positive'
                )
            ds_mesh = self.open_model_dataset(f'mesh_{resdir}.nc')
            ds = self.open_model_dataset(f'output_{resdir}_{mle}.nc')
            # daily output, starting at the end of the first day
            ds = ds.isel(Time=verify_day - 1).load()

            cell_mask = get_frontal_cell_mask(
                ds_mesh, frontal_zone_fraction
            ).values
            cells_on_edge = ds_mesh.cellsOnEdge.values - 1
            edges = np.flatnonzero(
                cell_mask[cells_on_edge[:, 0]] & cell_mask[cells_on_edge[:, 1]]
            )

            # MPAS-Ocean writes its mixed-layer index; Omega does not
            ml_index = ds.indMLD.values - 1 if 'indMLD' in ds else None
            psi_formula = compute_fk11_stream_function(
                config,
                ds_mesh,
                ds,
                edges,
                ds.dThreshMLD,
                ds.BruntVaisalaFreqTop,
                'mixed_layer_eddies_mle',
                model,
                ml_index=ml_index,
            )
            psi_model = compute_model_stream_function(
                config, ds_mesh, ds, edges, ds.normalMLEvelocity
            )
            consistent = get_consistent_edges(
                config,
                ds_mesh,
                ds,
                edges,
                ds.normalMLEvelocity,
                ds.dThreshMLD,
                model,
            )
            fraction = float(consistent.mean())
            psi_formula = psi_formula[consistent]
            psi_model = psi_model[consistent]
            if (
                psi_formula.size == 0
                or not np.isfinite(psi_formula).all()
                or not np.isfinite(psi_model).all()
                or not np.any(psi_formula)
            ):
                raise ValueError(
                    f'{resdir} {mle}: cannot compute normalized RMSE '
                    'without finite stream functions and a nonzero reference'
                )
            error = float(
                np.sqrt(((psi_model - psi_formula) ** 2).mean())
                / np.sqrt((psi_formula**2).mean())
            )
            logger.info(
                f'{resdir} {mle}: {100.0 * fraction:.1f}% of frontal-zone '
                f'edges have a consistent mixed-layer depth; normalized RMSE '
                f'of the parameterized stream function: {error:.3e} '
                f'(limit {tolerance:g})'
            )
            results.append(
                (
                    resdir,
                    mle,
                    fraction,
                    error,
                    psi_formula,
                    psi_model,
                )
            )

        _plot_verification(results)

        failed = []
        for resdir, mle, fraction, error, *_ in results:
            tolerance = section.getfloat(f'verify_tolerance_{resdir}')
            if not error <= tolerance:
                failed.append(
                    f'{resdir} {mle}: normalized RMSE {error:.3e} '
                    f'exceeds {tolerance:g}'
                )
            if not fraction >= min_fraction:
                failed.append(
                    f'{resdir} {mle}: only {100.0 * fraction:.1f}% of edges '
                    'have a consistent mixed-layer depth'
                )
        if failed:
            raise ValueError(
                'The parameterized stream function could not be verified:'
                '\n  ' + '\n  '.join(failed)
            )


def _plot_verification(results):
    """
    Plot the stream function each run's output implies against its formula
    on the frontal-zone edges with a consistent mixed-layer depth
    """
    ncols = len(results)
    with mplstyle_context():
        fig, axes = plt.subplots(
            1,
            ncols,
            figsize=(2.9 * ncols, 3.0),
            squeeze=False,
            constrained_layout=True,
        )
        for ax, (resdir, mle, _, error, psi_formula, psi_model) in zip(
            axes[0], results, strict=True
        ):
            ax.plot(psi_formula.ravel(), psi_model.ravel(), '.', markersize=1)
            limit = max(np.abs(psi_formula).max(), np.abs(psi_model).max())
            ax.plot([-limit, limit], [-limit, limit], 'k-', linewidth=0.5)
            ax.set_title(f'{resdir} {mle}\nNRMSE {error:.1e}', fontsize=9)
            ax.set_xlabel(r'formula $\Psi$ (m$^2$ s$^{-1}$)')
        axes[0, 0].set_ylabel(r'model $\Psi$ (m$^2$ s$^{-1}$)')
        fig.savefig('verification.png', bbox_inches='tight', dpi=150)
        plt.close(fig)
