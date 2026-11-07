"""
Tasks that compare the runs of several MISOMIP experiments on one mesh, or
of one experiment on several meshes
"""

import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf

from polaris import Task
from polaris.analysis.product_step import ProductStep
from polaris.tasks.e3sm.analysis.misomip.diagnostics import (
    TIME_MEAN_FILENAME,
    TIME_SERIES_FILENAME,
    add_geometry_inputs,
    isomip_mesh,
    read_initial_condition,
)
from polaris.tasks.e3sm.analysis.misomip.plots import (
    MAPS,
    SYMMETRIC_FIELDS,
    TIME_SERIES,
    get_color_range,
    get_map_mask,
    get_range_mask,
)
from polaris.tasks.e3sm.analysis.misomip.publish import MisomipPublish
from polaris.tasks.e3sm.analysis.misomip.runs import (
    EXPERIMENTS,
    MESH_NAMES,
    RUN_KINDS,
    get_configured_runs,
)
from polaris.tasks.e3sm.analysis.misomip.task import (
    RUN_LABELS,
    get_diagnostics_steps,
    get_resolution,
)
from polaris.viz.planar import plot_horiz_comparison
from polaris.viz.time_series import Series, plot_time_series


class SeriesComparison(ProductStep):
    """
    A step that overlays the time series of several runs of one kind and,
    optionally, maps their time means side by side

    Attributes
    ----------
    kind : str
        The kind of run, ``e3sm`` or ``standalone``, which is the products'
        group

    labels : list of str
        The label of each run

    include_maps : bool
        Whether to map the runs' time means side by side
    """

    def __init__(self, component, subdir, kind, runs, include_maps):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory for the step

        kind : str
            The kind of run

        runs : list of tuple
            The label and diagnostics step of each run

        include_maps : bool
            Whether to map the runs' time means side by side
        """
        super().__init__(
            component=component,
            name=f'{kind}_comparison',
            subdir=subdir,
            ntasks=1,
            cpus_per_task=1,
        )
        self.kind = kind
        self.labels = [label for label, _ in runs]
        self.include_maps = include_maps
        for index, (_, step) in enumerate(runs):
            filenames = [TIME_SERIES_FILENAME]
            if include_maps:
                filenames.append(TIME_MEAN_FILENAME)
                add_geometry_inputs(self, step, prefix=f'run{index}_')
            for filename in filenames:
                self.add_input_file(
                    filename=f'run{index}_{filename}',
                    work_dir_target=f'{step.path}/{filename}',
                )
            self.add_dependency(step, name=f'run{index}_diagnostics')

    def run(self):
        """
        Overlay the runs
        """
        series = [
            xr.open_dataset(f'run{index}_{TIME_SERIES_FILENAME}')
            for index in range(len(self.labels))
        ]
        for gallery, stem, title, ylabel, variables in TIME_SERIES:
            lines = []
            ds_data = xr.Dataset()
            for index, (label, ds) in enumerate(
                zip(self.labels, series, strict=True)
            ):
                for name, scale, line_label in variables:
                    if name not in ds:
                        continue
                    values = scale * ds[name]
                    ds_data[f'run{index}_{name}'] = values.rename(
                        {'Time': f'run{index}_Time'}
                    )
                    full_label = label
                    if line_label is not None:
                        full_label = f'{label}, {line_label}'
                    lines.append(
                        Series(ds.time.values, values.values, full_label)
                    )
            if not lines:
                continue
            ds_data.attrs['runs'] = ', '.join(self.labels)
            plot = f'{stem}.png'
            data = f'{stem}.nc'
            plot_time_series(lines, plot, ylabel=ylabel, title=title)
            write_netcdf(ds_data, data)
            self.add_product(
                plot=plot,
                data=data,
                group=self.kind,
                gallery=gallery,
                title=title,
            )
        if self.include_maps:
            self._map_side_by_side()

    def _map_side_by_side(self):
        """Map each run's time means, each on its own mesh"""
        meshes = []
        means = []
        floating = []
        for index in range(len(self.labels)):
            ds_init = read_initial_condition(prefix=f'run{index}_')
            meshes.append(isomip_mesh(ds_init))
            means.append(xr.open_dataset(f'run{index}_{TIME_MEAN_FILENAME}'))
            floating.append(ds_init.landIceFloatingFraction > 0.0)
        for gallery, name, title, scale, units, cmap, where in MAPS:
            fields = [scale * ds_mean[name] for ds_mean in means]
            on_cells = ['nCells' in field.dims for field in fields]
            shown = [
                get_map_mask(ds_mean, where) if cells else None
                for ds_mean, cells in zip(means, on_cells, strict=True)
            ]
            counted = [
                get_range_mask(ds_mean, mask) if cells else None
                for ds_mean, mask, cells in zip(
                    means, shown, on_cells, strict=True
                )
            ]
            masks = None
            if any(mask is not None for mask in shown):
                masks = shown
            vmin, vmax = _shared_range(self.config, name, fields, counted)
            stem = f'{name}_maps'
            plot = f'{stem}.png'
            data = f'{stem}.nc'
            plot_horiz_comparison(
                meshes,
                fields,
                self.labels,
                plot,
                cmap=cmap,
                cmap_title=units,
                field_masks=masks,
                vmin=vmin,
                vmax=vmax,
                include_difference=False,
                boundaries=floating,
                suptitle=title,
            )
            ds_data = xr.Dataset()
            for index, field in enumerate(fields):
                dims = {dim: f'run{index}_{dim}' for dim in field.dims}
                ds_data[f'run{index}'] = field.rename(dims)
            ds_data.attrs['runs'] = ', '.join(self.labels)
            write_netcdf(ds_data, data)
            self.add_product(
                plot=plot,
                data=data,
                group=self.kind,
                gallery=gallery,
                title=title,
            )


class MisomipExperimentsTask(Task):
    """
    A task that compares the runs of the MISOMIP experiments on one pair of
    meshes, one kind of run at a time

    Attributes
    ----------
    mesh_name : str
        The pair of meshes
    """

    def __init__(self, component, config, mesh_name):
        """
        Create the task

        Parameters
        ----------
        component : polaris.Component
            The e3sm/analysis component

        config : polaris.config.PolarisConfigParser
            The config shared by the MISOMIP analysis tasks

        mesh_name : str
            The pair of meshes
        """
        super().__init__(
            component=component,
            name=f'misomip_experiments_{mesh_name}',
            subdir=f'{mesh_name}/misomip/experiments',
        )
        self.mesh_name = mesh_name
        self.set_shared_config(config, link='misomip_analysis.cfg')

    def configure(self):
        """
        Build the steps from the runs the user's config names
        """
        super().configure()
        groups: dict[str, list] = {kind: [] for kind in RUN_KINDS}
        resolution = get_resolution(self.mesh_name)
        for experiment in EXPERIMENTS:
            runs = get_configured_runs(self.config, self.mesh_name, experiment)
            steps = get_diagnostics_steps(
                self.component, self.config, self.mesh_name, experiment, runs
            )
            for kind, step in steps.items():
                label = f'{RUN_LABELS[kind]} {experiment}, {resolution}'
                groups[kind].append((label, step, runs[kind].key))
        _setup_comparison_steps(
            self,
            groups,
            include_maps=False,
            relative_path=f'{self.mesh_name}/experiments',
            missing=(
                f'Fewer than two experiments on {self.mesh_name} have runs '
                f'of the same kind to compare.'
            ),
        )


class MisomipResolutionsTask(Task):
    """
    A task that compares the runs of one MISOMIP experiment on the 4 and
    2 km ocean meshes, one kind of run at a time

    Attributes
    ----------
    experiment : str
        The experiment
    """

    def __init__(self, component, config, experiment):
        """
        Create the task

        Parameters
        ----------
        component : polaris.Component
            The e3sm/analysis component

        config : polaris.config.PolarisConfigParser
            The config shared by the MISOMIP analysis tasks

        experiment : str
            The experiment
        """
        super().__init__(
            component=component,
            name=f'misomip_resolutions_{experiment}',
            subdir=f'misomip/resolutions/{experiment}',
        )
        self.experiment = experiment
        self.set_shared_config(config, link='misomip_analysis.cfg')

    def configure(self):
        """
        Build the steps from the runs the user's config names
        """
        super().configure()
        groups: dict[str, list] = {kind: [] for kind in RUN_KINDS}
        for mesh_name in MESH_NAMES:
            runs = get_configured_runs(self.config, mesh_name, self.experiment)
            steps = get_diagnostics_steps(
                self.component, self.config, mesh_name, self.experiment, runs
            )
            for kind, step in steps.items():
                label = f'{RUN_LABELS[kind]}, {get_resolution(mesh_name)}'
                groups[kind].append((label, step, runs[kind].key))
        _setup_comparison_steps(
            self,
            groups,
            include_maps=True,
            relative_path=f'resolutions/{self.experiment}',
            missing=(
                f'Fewer than two meshes have runs of {self.experiment} of '
                f'the same kind to compare.'
            ),
        )


def _setup_comparison_steps(
    task, groups, include_maps, relative_path, missing
):
    """Replace a comparison task's steps with those for its runs"""
    for step in list(task.steps.values()):
        task.remove_step(step)
    products = []
    for kind, members in groups.items():
        if len(members) < 2:
            continue
        for _, step, _ in members:
            task.add_step(step)
        key = '_'.join(member_key for _, _, member_key in members)
        step = task.component.get_or_create_shared_step(
            step_cls=SeriesComparison,
            subdir=f'{task.subdir}/{kind}_{key}',
            config=task.config,
            config_filename='misomip_analysis.cfg',
            kind=kind,
            runs=[(label, step) for label, step, _ in members],
            include_maps=include_maps,
        )
        task.add_step(step)
        products.append(step)
    task.add_step(
        MisomipPublish(
            component=task.component,
            subdir=f'{task.subdir}/publish',
            product_steps=products,
            relative_path=relative_path,
            missing=missing,
        )
    )


def _shared_range(config, name, fields, counted):
    """The color range of a field's maps side by side: the configured
    range, or the range of every run's field where it counts"""
    vmin, vmax = get_color_range(config, name)
    if vmin is not None:
        return vmin, vmax
    chunks = []
    for field, cells in zip(fields, counted, strict=True):
        shown = field if cells is None else field.where(cells)
        chunks.append(shown.values.ravel())
    values = np.concatenate(chunks)
    vmin = float(np.nanmin(values))
    vmax = float(np.nanmax(values))
    if name in SYMMETRIC_FIELDS:
        limit = max(abs(vmin), abs(vmax))
        vmin, vmax = -limit, limit
    return vmin, vmax
