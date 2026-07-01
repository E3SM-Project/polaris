import os

import cmocean  # noqa: F401
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
from matplotlib.font_manager import FontProperties
from mpas_tools.ocean.viz.transect import compute_transect, plot_transect
from mpas_tools.viz.mpas_to_xdmf.mpas_to_xdmf import MpasToXdmf

from polaris.ocean.model import OceanIOStep
from polaris.viz import get_viz_defaults, plot_global_mpas_field


class VizInitStep(OceanIOStep):
    """
    A step for visualizing the realistic global ocean initial condition and
    vertical-coordinate datasets for either MPAS-Ocean or Omega.

    The step is model-agnostic: it reads through
    :py:meth:`~polaris.ocean.model.OceanIOStep.open_model_dataset` (which maps
    Omega variable names to their MPAS-Ocean equivalents and reconstructs the
    geometric ``layerThickness`` from ``PseudoThickness``) and
    :py:meth:`~polaris.ocean.model.OceanIOStep.open_vert_coord_dataset`.

    It produces:

    * a summary figure of histograms (a de-Haney'd port of Compass'
      ``plot_initial_state``),
    * a vertical-coordinate structure figure,
    * global native-mesh maps of temperature and salinity at several depths
      plus surface and bottom, and topography/column diagnostics,
    * multi-basin vertical transects of temperature and salinity,
    * (Omega only) a stratification check using the TEOS-10 in-situ density,
      and
    * XDMF/HDF5 exports of the ``init`` and (Omega) ``vert_coord`` datasets for
      ParaView.

    Attributes
    ----------
    init_step : polaris.Step
        The step that produces ``init.nc`` (and ``vert_coord.nc`` for Omega).

    cull_mesh_step : polaris.Step
        The cull-mesh step that produces the MPAS horizontal mesh.
    """

    def __init__(self, component, subdir, init_step, cull_mesh_step):
        """
        Create the step.

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the step belongs to.

        subdir : str
            The subdirectory for the step.

        init_step : polaris.Step
            The step that produces ``init.nc`` (and ``vert_coord.nc`` for
            Omega).

        cull_mesh_step : polaris.Step
            The step that produces ``culled_ocean_mesh.nc``.
        """
        super().__init__(
            component=component,
            name='viz',
            subdir=subdir,
        )
        self.init_step = init_step
        self.cull_mesh_step = cull_mesh_step

    def setup(self):
        """
        Declare input and output files based on the configured ocean model.
        """
        super().setup()
        model = self.config.get('ocean', 'model')

        self.add_input_file(
            filename='mesh.nc',
            work_dir_target=os.path.join(
                self.cull_mesh_step.path,
                'culled_ocean_mesh.nc',
            ),
        )
        self.add_input_file(
            filename='init.nc',
            work_dir_target=os.path.join(self.init_step.path, 'init.nc'),
        )
        if model == 'omega':
            self.add_input_file(
                filename='vert_coord.nc',
                work_dir_target=os.path.join(
                    self.init_step.path, 'vert_coord.nc'
                ),
            )

        self.add_output_file('initial_state_summary.png')
        self.add_output_file('vertical_coordinate.png')

    def run(self):
        """
        Create the visualizations and ParaView exports.
        """
        config = self.config
        model = config.get('ocean', 'model')

        ds_mesh = xr.open_dataset('mesh.nc')
        ds_init = self.open_model_dataset(
            'init.nc', config, decode_timedelta=False
        )
        ds_vert_coord = self.open_vert_coord_dataset(
            ds_init, decode_timedelta=False
        )
        if 'Time' in ds_init.sizes:
            ds_init = ds_init.isel(Time=0)
        if 'Time' in ds_vert_coord.sizes:
            ds_vert_coord = ds_vert_coord.isel(Time=0)

        _plot_summary(model, ds_mesh, ds_init, ds_vert_coord)
        _plot_vertical_coord(ds_init, ds_vert_coord)
        self._plot_global_maps(model, ds_mesh, ds_init, ds_vert_coord)
        self._plot_transects(model, ds_mesh, ds_init, ds_vert_coord)
        self._export_xdmf(model, ds_mesh)

    def _plot_global_maps(self, model, ds_mesh, ds_init, ds_vert_coord):
        """
        Plot global native-mesh maps of temperature/salinity (at depths plus
        surface and bottom), topography/column diagnostics, and (Omega) native
        pressure and in-situ density.
        """
        config = self.config
        section_name = 'realistic_global_init_viz'
        section = config[section_name]
        projection_name = section.get('projection')
        central_longitude = section.getfloat('central_longitude')
        depths = config.getlist(section_name, 'depths', dtype=float)

        viz_dict = get_viz_defaults()
        kbot = (ds_vert_coord.maxLevelCell - 1).astype(int)
        kbot_da = xr.DataArray(kbot.values, dims='nCells')

        # At initialization layerThickness equals restingThickness (both the
        # geometric layer thickness); it is present and geometric for both
        # models (reconstructed from PseudoThickness for Omega), whereas
        # restingThickness has no Omega equivalent in the vert_coord file.
        layer_thickness = ds_init.layerThickness

        tracer_names = ['temperature', 'salinity']
        if model == 'omega' and 'Density' in ds_init:
            tracer_names.append('Density')

        # (field, out_name, label) tuples for cell-centered fields
        plots = []
        for var_name in tracer_names:
            if var_name not in ds_init:
                continue
            units = _units_for(viz_dict, var_name)
            field = ds_init[var_name]
            for depth in depths:
                z_index = _z_index_for_depth(layer_thickness, depth)
                plots.append(
                    (
                        field.isel(nVertLevels=z_index),
                        f'{var_name}_z{int(depth)}m',
                        f'{var_name} at {int(depth)} m [{units}]',
                        var_name,
                    )
                )
            plots.append(
                (
                    field.isel(nVertLevels=0),
                    f'{var_name}_surface',
                    f'{var_name} at surface [{units}]',
                    var_name,
                )
            )
            plots.append(
                (
                    field.isel(nVertLevels=kbot_da),
                    f'{var_name}_bottom',
                    f'{var_name} at seafloor [{units}]',
                    var_name,
                )
            )

        # topography / column diagnostics
        column_thickness = ds_vert_coord.bottomDepth + ds_init['ssh']
        plots.append(
            (
                ds_vert_coord.bottomDepth,
                'bottomDepth',
                f'bottomDepth [{_units_for(viz_dict, "bottomDepth")}]',
                'bottomDepth',
            )
        )
        plots.append((ds_init['ssh'], 'ssh', 'ssh [m]', 'ssh'))
        plots.append(
            (
                ds_vert_coord.maxLevelCell,
                'maxLevelCell',
                'maxLevelCell',
                'default',
            )
        )
        plots.append(
            (
                column_thickness,
                'columnThickness',
                'column thickness [m]',
                'bottomDepth',
            )
        )

        if model == 'omega':
            surf_p = _first_present(ds_init, ['surfacePressure'])
            bot_p = _first_present(
                ds_init, ['bottomPressure', 'BottomPressure']
            )
            for name, label in [
                (surf_p, 'surfacePressure'),
                (bot_p, 'bottomPressure'),
            ]:
                if name is None:
                    continue
                da = ds_init[name]
                da = _to_mpas_dims(da, self.component)
                plots.append((da, label, f'{label} [Pa]', 'default'))

        descriptor = None
        for da, out_name, label, key in plots:
            cmap = _cmap_for(viz_dict, key)
            _set_colormap(config, section_name, cmap, da)
            plot_global_mpas_field(
                mesh_filename='mesh.nc',
                da=da,
                out_filename=f'{out_name}.png',
                config=config,
                colormap_section=section_name,
                descriptor=descriptor,
                colorbar_label=label,
                title=label,
                plot_land=True,
                projection_name=projection_name,
                central_longitude=central_longitude,
            )
            plt.close('all')

    def _plot_transects(self, model, ds_mesh, ds_init, ds_vert_coord):
        """
        Plot multi-basin vertical transects of temperature/salinity (and
        in-situ density for Omega).
        """
        config = self.config
        section_name = 'realistic_global_init_viz_transects'
        names = config.getlist(section_name, 'transects', dtype=str)
        if not names:
            return

        viz_dict = get_viz_defaults()
        var_names = ['temperature', 'salinity']
        if model == 'omega' and 'Density' in ds_init:
            var_names.append('Density')

        for name in names:
            coords = config.getlist(section_name, name, dtype=float)
            if len(coords) < 4 or len(coords) % 2 != 0:
                raise ValueError(
                    f'Transect {name} must have an even number (>= 4) of '
                    'values giving alternating lon, lat waypoints'
                )
            x = xr.DataArray(data=coords[0::2], dims='nPoints')
            y = xr.DataArray(data=coords[1::2], dims='nPoints')
            ds_transect = compute_transect(
                x=x,
                y=y,
                ds_horiz_mesh=ds_mesh,
                layer_thickness=ds_init.layerThickness,
                bottom_depth=ds_vert_coord.bottomDepth,
                min_level_cell=ds_vert_coord.minLevelCell - 1,
                max_level_cell=ds_vert_coord.maxLevelCell - 1,
                spherical=True,
            )
            for var_name in var_names:
                if var_name not in ds_init:
                    continue
                units = _units_for(viz_dict, var_name)
                cmap = _cmap_for(viz_dict, var_name)
                plot_transect(
                    ds_transect=ds_transect,
                    mpas_field=ds_init[var_name],
                    title=f'{var_name} - {name}',
                    out_filename=f'{var_name}_transect_{name}.png',
                    interface_color='grey',
                    colorbar_label=units,
                    cmap=cmap,
                    color_start_and_end=True,
                )
                plt.close('all')

    def _export_xdmf(self, model, ds_mesh):
        """
        Export the ``init`` and (Omega) ``vert_coord`` datasets to XDMF/HDF5
        for ParaView.

        For Omega the native variable names are preserved and only the
        dimensions are renamed to their MPAS-Ocean equivalents (required by
        :py:class:`~mpas_tools.viz.mpas_to_xdmf.MpasToXdmf`).
        """
        filenames = ['init.nc']
        out_dirs = ['xdmf/init']
        if model == 'omega':
            filenames.append('vert_coord.nc')
            out_dirs.append('xdmf/vert_coord')

        for filename, out_dir in zip(filenames, out_dirs, strict=True):
            ds_data = xr.open_dataset(filename)
            if model == 'omega':
                ds_data = _rename_dims_to_mpas(ds_data, self.component)
            # MpasToXdmf requires every non-topology dimension (e.g.
            # nVertLevels) to be listed in extra_dims; keep all indices so
            # each 3D field is unwrapped into one 2D field per level.
            basic_dims = ('Time', 'nCells', 'nEdges', 'nVertices')
            extra_dims = {
                dim: list(range(ds_data.sizes[dim]))
                for dim in ds_data.dims
                if dim not in basic_dims
            }
            converter = MpasToXdmf(ds=ds_data, ds_mesh=ds_mesh)
            converter.convert_to_xdmf(out_dir=out_dir, extra_dims=extra_dims)


def _plot_summary(model, ds_mesh, ds_init, ds_vert_coord):
    """
    Create a summary figure of histograms of the initial condition (a
    de-Haney'd port of Compass' ``plot_initial_state``).
    """
    n_cells = ds_mesh.sizes['nCells']
    n_vert_levels = ds_init.sizes['nVertLevels']

    max_level_cell = ds_vert_coord.maxLevelCell.values - 1
    cell_mask = np.zeros((n_cells, n_vert_levels), bool)
    for k in range(n_vert_levels):
        cell_mask[:, k] = k <= max_level_cell
    cell_mask = xr.DataArray(data=cell_mask, dims=('nCells', 'nVertLevels'))

    fig = plt.figure(figsize=(16.0, 16.0))

    txt = (
        f'{model} initial state\n'
        f'number cells: {n_cells}\n'
        f'number cells, millions: {n_cells / 1.0e6:6.3f}\n'
        f'number layers: {n_vert_levels}\n\n'
        '  min val   max val  variable name\n'
    )

    txt = _hist(
        fig,
        2,
        ds_vert_coord.maxLevelCell,
        'maxLevelCell',
        txt,
        bins=n_vert_levels - 4,
        log=False,
    )
    txt = _hist(
        fig,
        3,
        ds_vert_coord.bottomDepth,
        'bottomDepth',
        txt,
        bins=n_vert_levels - 4,
        log=False,
    )
    txt = _hist(
        fig, 4, ds_init.temperature.where(cell_mask), 'temperature', txt
    )
    txt = _hist(fig, 5, ds_init.salinity.where(cell_mask), 'salinity', txt)
    txt = _hist(
        fig,
        6,
        ds_init.layerThickness.where(cell_mask),
        'layerThickness (geometric)',
        txt,
    )

    native, native_name = _native_prognostic_thickness(model)
    txt = _hist(fig, 7, native, native_name, txt)

    txt = _hist(fig, 8, 1e-6 * ds_mesh.areaCell, r'cell area (km$^2$)', txt)
    txt = _hist(fig, 9, 1e-3 * ds_mesh.dcEdge, 'dcEdge (km)', txt)
    txt = _hist(
        fig,
        10,
        ds_init.ssh + ds_vert_coord.bottomDepth,
        'open ocean column thickness (m)',
        txt,
    )

    font = FontProperties()
    font.set_family('monospace')
    font.set_size(12)
    ax = fig.add_subplot(4, 3, 1)
    ax.text(0, 1, txt, verticalalignment='top', fontproperties=font)
    ax.axis('off')

    fig.tight_layout(pad=4.0)
    fig.savefig(
        'initial_state_summary.png', bbox_inches='tight', pad_inches=0.1
    )
    plt.close(fig)


def _plot_vertical_coord(ds_init, ds_vert_coord):
    """
    Plot the vertical-coordinate structure from the geometric layer thickness
    of the deepest column in the mesh.  There is no reference profile in this
    workflow, so the structure is derived from the initial (resting) geometric
    layer thickness directly.  ``layerThickness`` equals the resting thickness
    at initialization and is available for both models (reconstructed from
    ``PseudoThickness`` for Omega), whereas ``restingThickness`` has no Omega
    equivalent in the vert_coord file.
    """
    kmax = int(ds_vert_coord.maxLevelCell.max().values)
    deepest = int(np.argmax(ds_vert_coord.maxLevelCell.values))
    thickness = ds_init.layerThickness.isel(nCells=deepest).values[:kmax]
    mid_depth = np.cumsum(thickness) - 0.5 * thickness
    z_ind = np.arange(1, kmax + 1)

    fig = plt.figure(figsize=(16.0, 8.0))

    ax = fig.add_subplot(2, 2, 1)
    ax.plot(z_ind, mid_depth, '.')
    ax.invert_yaxis()
    ax.set_xlabel('vertical index (one-based)')
    ax.set_ylabel('layer mid-depth [m]')
    ax.grid()

    ax = fig.add_subplot(2, 2, 2)
    ax.plot(thickness, mid_depth, '.')
    ax.invert_yaxis()
    ax.set_xlabel('layer thickness [m]')
    ax.set_ylabel('layer mid-depth [m]')
    ax.grid()

    ax = fig.add_subplot(2, 2, 3)
    ax.plot(z_ind, thickness, '.')
    ax.set_xlabel('vertical index (one-based)')
    ax.set_ylabel('layer thickness [m]')
    ax.grid()

    txt = (
        f'number layers: {ds_init.sizes["nVertLevels"]}\n'
        f'deepest column layers: {kmax}\n'
        f'min thickness: {np.amin(thickness):8.2f}\n'
        f'max thickness: {np.amax(thickness):8.2f}\n'
        f'max bottom depth: {ds_vert_coord.bottomDepth.max().values:8.2f}'
    )
    ax = fig.add_subplot(2, 2, 4)
    ax.text(0, 0, txt, fontsize=12)
    ax.axis('off')

    fig.savefig('vertical_coordinate.png')
    plt.close(fig)


def _native_prognostic_thickness(model):
    """
    Read the model's native prognostic layer-thickness variable from the raw
    (unmapped) output file, returning the DataArray and a display name.
    """
    if model == 'omega':
        ds = xr.open_dataset('init.nc')
        return ds['PseudoThickness'], 'PseudoThickness (Omega)'
    ds = xr.open_dataset('init.nc')
    return ds['layerThickness'], 'layerThickness (MPAS-Ocean)'


def _hist(fig, index, da, name, txt, bins=100, log=True):
    """
    Add a histogram subplot (4x3 grid) of the finite values of ``da`` and
    append a min/max line to ``txt``.
    """
    ax = fig.add_subplot(4, 3, index)
    values = np.asarray(da.values).ravel()
    values = values[np.isfinite(values)]
    ax.hist(values, bins=bins, log=log)
    ax.set_xlabel(name)
    ax.set_ylabel('frequency')
    if values.size > 0:
        vmin = values.min()
        vmax = values.max()
    else:
        vmin = np.nan
        vmax = np.nan
    return f'{txt}{vmin:9.2e} {vmax:9.2e} {name}\n'


def _z_index_for_depth(layer_thickness, z_target):
    """
    Return the vertical index whose mean bottom depth is closest to
    ``z_target`` (in metres), using the cumulative layer thickness averaged
    over cells (mirrors ``customizable_viz``).
    """
    z_bottom = layer_thickness.cumsum(dim='nVertLevels')
    dz = z_bottom.mean(dim='nCells') - z_target
    z_index = int(np.argmin(np.abs(dz.values)))
    if dz.values[z_index] > 0 and z_index > 0:
        z_index -= 1
    return z_index


def _first_present(ds, names):
    """Return the first name in ``names`` present in ``ds``, else ``None``."""
    for name in names:
        if name in ds:
            return name
    return None


def _units_for(viz_dict, var_name):
    """Return the units string for ``var_name`` from the viz defaults."""
    key = var_name if var_name in viz_dict else 'default'
    return viz_dict[key]['units']


def _cmap_for(viz_dict, var_name):
    """Return the colormap name for ``var_name`` from the viz defaults."""
    key = var_name if var_name in viz_dict else 'default'
    return viz_dict[key]['colormap']


def _set_colormap(config, section_name, cmap, da):
    """
    Set ``colormap_name`` and ``norm_args`` in ``section_name`` from the data
    range of ``da`` for use by ``plot_global_mpas_field``.
    """
    values = np.asarray(da.values).ravel()
    values = values[np.isfinite(values)]
    if values.size > 0:
        vmin = float(values.min())
        vmax = float(values.max())
    else:
        vmin, vmax = 0.0, 1.0
    if cmap == 'cmo.balance':
        vmax = max(abs(vmin), abs(vmax))
        vmin = -vmax
    config.set(section_name, 'colormap_name', value=cmap)
    config.set(
        section_name,
        'norm_args',
        value='{"vmin": ' + str(vmin) + ', "vmax": ' + str(vmax) + '}',
    )


def _to_mpas_dims(da, component):
    """
    Rename any Omega dimension names on ``da`` to their MPAS-Ocean equivalents.
    """
    rename = {
        omega: mpaso
        for mpaso, omega in component.mpaso_to_omega_dim_map.items()
        if omega in da.dims
    }
    if rename:
        da = da.rename(rename)
    return da


def _rename_dims_to_mpas(ds, component):
    """
    Rename Omega dimension names in ``ds`` to their MPAS-Ocean equivalents,
    leaving variable names unchanged (as required by ``MpasToXdmf``).
    """
    rename = {
        omega: mpaso
        for mpaso, omega in component.mpaso_to_omega_dim_map.items()
        if omega in ds.dims
    }
    if rename:
        ds = ds.rename(rename)
    return ds
