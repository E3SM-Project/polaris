import cmocean  # noqa: F401
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

from polaris.ocean.model import OceanIOStep
from polaris.tasks.ocean.mixed_layer_eddies.diagnostics import (
    compute_buoyancy_gradient,
    compute_eddy_overturning,
    compute_mu,
    fit_mu_amplitude,
    get_frontal_cell_mask,
    get_frontal_lines,
)
from polaris.tasks.ocean.mixed_layer_eddies.flux import (
    analyze_combined_flux,
    get_snapshot_days,
)
from polaris.tasks.ocean.mixed_layer_eddies.viz import plot_surface_salinity
from polaris.viz import mplstyle_context

# the days at which surface salinity is plotted
SURFACE_SALINITY_DAYS = (1, 5, 10, 15)

# the segments of the resolved run, in order
SEGMENTS = ('spinup', 'eddies')


class Analysis(OceanIOStep):
    """
    A step for diagnosing the eddy overturning of the resolved run and
    comparing it with the scaling of Fox-Kemper et al. (2008), as in
    Shrestha & Manucharyan (2022)
    """

    def __init__(self, component, indir, resolved_steps):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        indir : str
            The directory the step is in, to which ``name`` will be appended

        resolved_steps : dict of polaris.Step
            The shared ``init`` step and the forward steps of each segment of
            the resolved run
        """
        super().__init__(component=component, name='analysis', indir=indir)
        init = resolved_steps['init']
        self.add_input_file(
            filename='mesh.nc', work_dir_target=f'{init.path}/culled_mesh.nc'
        )
        self.add_input_file(
            filename='eddy_output.nc',
            work_dir_target=f'{resolved_steps["eddies"].path}/eddy_output.nc',
        )
        for name in SEGMENTS:
            self.add_input_file(
                filename=f'output_{name}.nc',
                work_dir_target=f'{resolved_steps[name].path}/output.nc',
            )
        self.add_output_file(filename='eddy_overturning.nc')
        self.add_output_file(filename='surface_salinity.png')
        self.add_output_file(filename='eddy_overturning_profile.png')
        self.add_output_file(filename='eddy_overturning_section.png')
        self.add_output_file(filename='combined_buoyancy_flux.png')
        self.add_output_file(filename='combined_buoyancy_flux.csv')
        self.add_output_file(filename='combined_buoyancy_flux_average.csv')

    def run(self):
        """
        Run this step of the task
        """
        config = self.config
        logger = self.logger
        section = config['mixed_layer_eddies_analysis']
        frontal_zone_fraction = section.getfloat('frontal_zone_fraction')
        ce = section.getfloat('ce')
        psi_plus_min = section.getfloat('psi_plus_min')
        psi_plus_max = section.getfloat('psi_plus_max')
        ml_depth = config.getfloat('mixed_layer_eddies', 'mixed_layer_depth')
        bins = np.arange(
            section.getfloat('salinity_bin_min'),
            section.getfloat('salinity_bin_max')
            + 0.5 * section.getfloat('salinity_bin_width'),
            section.getfloat('salinity_bin_width'),
        )

        ds_mesh = self.open_model_dataset('mesh.nc')
        ds_out = self.open_model_dataset('eddy_output.nc')
        forward = config['mixed_layer_eddies_forward']
        start = forward.getfloat('spinup_duration')
        end = start + forward.getfloat('eddy_window_duration')
        days = get_snapshot_days(ds_out)
        ds_out = ds_out.isel(
            Time=np.flatnonzero((days > start) & (days <= end))
        )
        ntimes = ds_out.sizes['Time']
        if ntimes == 0:
            raise ValueError('No snapshots in the eddy overturning window')
        logger.info(f'Diagnosing the eddy overturning from {ntimes} snapshots')

        lines = get_frontal_lines(ds_mesh, frontal_zone_fraction)
        cell_mask = get_frontal_cell_mask(ds_mesh, frontal_zone_fraction)
        snapshots = (ds_out.isel(Time=index).load() for index in range(ntimes))
        ds_psi = compute_eddy_overturning(lines, snapshots, bins, config)

        buoyancy_gradient = np.mean(
            [
                float(
                    compute_buoyancy_gradient(
                        config,
                        ds_mesh,
                        ds_out.isel(Time=index).load(),
                        cell_mask,
                        ml_depth,
                    )
                )
                for index in range(ntimes)
            ]
        )
        f = float(np.abs(ds_mesh.fCell).mean())
        scale = ce * ml_depth**2 * buoyancy_gradient / f

        z_profile = np.linspace(0.0, -1.5 * ml_depth, 61)
        psi_lines = [
            np.interp(
                z_profile,
                ds_psi.zClass.isel(nLines=index).values[::-1],
                ds_psi.psiEddy.isel(nLines=index).values[::-1],
            )
            for index in range(ds_psi.sizes['nLines'])
        ]
        psi_profile = np.mean(psi_lines, axis=0)
        amplitude = fit_mu_amplitude(psi_profile, z_profile, ml_depth)
        psi_plus = amplitude / scale

        ds_psi['zProfile'] = ('nProfile', z_profile)
        ds_psi['psiEddyProfile'] = ('nProfile', psi_profile)
        ds_psi.attrs['buoyancy_gradient'] = buoyancy_gradient
        ds_psi.attrs['psi_plus'] = psi_plus
        ds_psi.to_netcdf('eddy_overturning.nc')

        logger.info(
            f'Frontal-zone mixed-layer buoyancy gradient: '
            f'{buoyancy_gradient:.3e} s-2\n'
            f'FFH08 scale C_e H^2 b_y / |f|: {scale:.3e} m2 s-1\n'
            f'Fitted eddy overturning amplitude: {amplitude:.3e} m2 s-1\n'
            f'Normalized overturning Psi+: {psi_plus:.3f}'
        )

        _plot_profile(z_profile, psi_profile / scale, ml_depth, psi_plus)
        _plot_section(ds_psi, ml_depth)
        self._plot_surface_salinity(ds_mesh)

        analyze_combined_flux(
            self,
            [('resolved', 'mesh.nc', 'eddy_output.nc', False)],
        )

        if not psi_plus_min <= abs(psi_plus) <= psi_plus_max:
            raise ValueError(
                f'|Psi+| = {abs(psi_plus):.3f} is outside the range '
                f'[{psi_plus_min}, {psi_plus_max}]'
            )

    def _plot_surface_salinity(self, ds_mesh):
        """
        Plot the surface salinity of the resolved run at several days from
        its daily output
        """
        snapshots: list[xr.Dataset] = []
        for name in SEGMENTS:
            ds = self.open_model_dataset(f'output_{name}.nc')
            snapshots.extend(
                ds.isel(Time=index) for index in range(ds.sizes['Time'])
            )
        # daily output, starting at the end of the first day
        selected = [
            (day, snapshots[day - 1].load())
            for day in SURFACE_SALINITY_DAYS
            if day <= len(snapshots)
        ]
        surface = selected[0][1].salinity.isel(nVertLevels=0)
        vmin = float(surface.min())
        vmax = float(surface.max())
        with mplstyle_context():
            fig, axes = plt.subplots(
                2, 2, figsize=(10.0, 7.0), constrained_layout=True
            )
            collection = None
            for ax, (day, ds) in zip(axes.ravel(), selected, strict=False):
                collection = plot_surface_salinity(
                    ax, ds_mesh, ds, f'day {day}', vmin, vmax
                )
            for ax in axes.ravel()[len(selected) :]:
                ax.set_axis_off()
            assert collection is not None
            fig.colorbar(
                collection,
                ax=axes,
                extend='both',
                shrink=0.7,
                label=r'surface salinity (g kg$^{-1}$)',
            )
            fig.savefig('surface_salinity.png', dpi=150)
            plt.close(fig)


def _plot_profile(z, psi_normalized, ml_depth, psi_plus):
    """
    Plot the normalized eddy overturning against the structure function
    """
    with mplstyle_context():
        fig, ax = plt.subplots(figsize=(4.5, 5.0))
        ax.plot(psi_normalized, z, label=r'$\Psi / (C_e H^2 b_y / |f|)$')
        ax.plot(
            psi_plus * compute_mu(z, ml_depth),
            z,
            '--',
            label=rf'{psi_plus:.2f} $\mu(z)$',
        )
        ax.plot(compute_mu(z, ml_depth), z, ':', label=r'$\mu(z)$')
        ax.set_xlabel('normalized stream function')
        ax.set_ylabel('z (m)')
        ax.legend()
        fig.savefig('eddy_overturning_profile.png', bbox_inches='tight')
        plt.close(fig)


def _plot_section(ds_psi, ml_depth):
    """
    Plot the eddy overturning across the frontal zone against the mean
    depth of each salinity class
    """
    nclasses = ds_psi.sizes['nBinsP1']
    y = 1e-3 * np.repeat(ds_psi.yLine.values[:, np.newaxis], nclasses, axis=1)
    z = ds_psi.zClass.values
    psi = ds_psi.psiEddy.values
    vmax = np.abs(psi).max()
    with mplstyle_context():
        fig, ax = plt.subplots(figsize=(6.0, 4.0))
        mesh = ax.pcolormesh(
            y,
            z,
            psi,
            shading='gouraud',
            cmap='cmo.balance',
            vmin=-vmax,
            vmax=vmax,
        )
        fig.colorbar(mesh, ax=ax, label=r'$\Psi$ (m$^2$ s$^{-1}$)')
        ax.set_ylim(-2.0 * ml_depth, 0.0)
        ax.set_xlabel('y (km)')
        ax.set_ylabel('z (m)')
        fig.savefig('eddy_overturning_section.png', bbox_inches='tight')
        plt.close(fig)
