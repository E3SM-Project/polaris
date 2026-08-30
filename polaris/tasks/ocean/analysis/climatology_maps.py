import os

import xarray as xr
from mpas_tools.io import write_netcdf

from polaris.ocean.heat_content import heat_content
from polaris.ocean.model import get_layer_mass
from polaris.ocean.model.layer_mass import MASS_THICKNESS_VARIABLES
from polaris.ocean.vertical.diagnostics import get_z_mid_and_interface
from polaris.ocean.vertical.elevation import (
    apply_vertical_reduction,
    elevation_range_weights,
    get_valid_level_range,
    parse_vertical_reduction,
    range_bound_label,
)
from polaris.tasks.ocean.analysis.analysis_step import AnalysisStep
from polaris.tasks.ocean.analysis.climatology import find_climatology_file
from polaris.tasks.ocean.analysis.config_sections import map_section
from polaris.tasks.ocean.analysis.heat_content_config import (
    get_elevation_ranges,
    get_specific_heat,
)
from polaris.tasks.ocean.analysis.sim_files import year_range_key
from polaris.viz import plot_global_mpas_field

# The field groups maps are chunked into.
#
# A group is the unit of *shared computation*, and therefore the unit of work:
# one step per group.  The two velocity components share one vector
# reconstruction, and heat content over several elevation ranges shares one set
# of layer weights, so each is worth computing once.  Temperature, salinity and
# ssh are groups of one only because they share nothing.
#
# It is deliberately not a presentation grouping.  How products are gathered
# for a reader is carried by the manifest's ``group`` and ``gallery`` facets,
# which the publication layer adds, so that re-chunking the work does not
# rearrange the gallery.  A group of two fields can appear as two galleries,
# and two groups can appear under one heading.
#
# Heat content reads no field of its own, since it is derived from temperature
# and the layer masses.
FIELD_GROUPS = {
    'temperature': ('temperature',),
    'salinity': ('salinity',),
    'velocity': ('velocityZonal', 'velocityMeridional'),
    'ssh': ('ssh',),
    'mixed_layer_depth': ('mixedLayerDepth',),
    'heat_content': ('heat_content',),
}

# Heat content is a field group of the maps rather than a product of its own,
# and it is not one of the fields a user lists, so it is always present
DERIVED_FIELD_GROUPS = ('heat_content',)

# The one field that is computed rather than read.  It is spelled the way a
# config section is because it is Polaris's own diagnostic rather than a
# variable either model writes, so there is no model spelling to follow.
HEAT_CONTENT = 'heat_content'

# Heat content is written in J m-2, which is the unit it means, and plotted
# in GJ m-2, since the whole column at a typical ocean temperature is a few
# hundred of those rather than a few times 10^11 of the other
J_PER_GJ = 1.0e9


def get_field_groups(fields):
    """
    Get the field groups that cover a list of requested fields

    Parameters
    ----------
    fields : list of str
        The fields to plot, using MPAS-Ocean names, as listed in the
        ``[ocean_analysis_climatology] fields`` config option

    Returns
    -------
    field_groups : dict
        A mapping from the name of each group that is needed to the fields of
        that group that were requested, in the order the groups are defined

    Raises
    ------
    ValueError
        If a requested field belongs to no group
    """
    requested: dict = {}
    for field in fields:
        group = _group_for_field(field)
        requested.setdefault(group, []).append(field)

    field_groups = {}
    for group, group_fields in FIELD_GROUPS.items():
        if group in DERIVED_FIELD_GROUPS:
            field_groups[group] = list(group_fields)
        elif group in requested:
            field_groups[group] = requested[group]
    return field_groups


class ClimatologyMaps(AnalysisStep):
    """
    A step that plots maps of one field group from the climatology

    Attributes
    ----------
    field_group : str
        The name of the field group this step covers, which is the unit of
        shared computation rather than a heading products are gathered under

    fields : list of str
        The fields of that group that were requested
    """

    def __init__(
        self,
        component,
        subdir,
        field_group,
        fields,
        start_year,
        end_year,
        climatology,
    ):
        """
        Create a climatology map step for one field group

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the step belongs to

        subdir : str
            The subdirectory for the step

        field_group : str
            The name of the field group this step covers

        fields : list of str
            The fields of that group that were requested

        start_year : int
            The first year of the climatology, inclusive

        end_year : int
            The last year of the climatology, inclusive

        climatology : polaris.tasks.ocean.analysis.Climatology
            The climatology this step plots maps of.  It is a dependency
            rather than an input file because ``ncclimo`` names its output
            for the case and the dates, so the file names are not known
            until it has run.
        """
        super().__init__(
            component=component,
            name=field_group,
            subdir=subdir,
            start_year=start_year,
            end_year=end_year,
            ntasks=1,
            cpus_per_task=1,
        )
        self.field_group = field_group
        self.fields = list(fields)
        self._coords: dict = {}
        self.add_dependency(climatology, name='climatology')

    def setup(self):
        """
        Link the mesh the maps are plotted on and the vertical coordinate

        The vertical coordinate supplies the topmost and bottommost valid
        layer of each column, which the climatology does not carry.  The
        elevation of the layers themselves does come from the climatology,
        since it is the climatological mean of a geometry that moves.
        """
        sim_files = self.get_sim_files()
        self.add_sim_input_file(sim_files.mesh_filename(), 'mesh.nc')
        self.add_sim_input_file(
            sim_files.vert_coord_filename(), 'vert_coord.nc'
        )

    def run(self):
        """
        Plot a map of each field of this group, for each season and each
        vertical reduction that was asked for
        """
        self.log_inputs()
        config = self.config
        seasons = config.getlist('ocean_analysis_climatology', 'plot_seasons')
        specs = config.getlist('ocean_analysis_climatology', 'elevations')
        reductions = [parse_vertical_reduction(spec) for spec in specs]
        ranges = get_elevation_ranges(config)
        self._coords = self._mesh_coords()
        min_level_cell, max_level_cell = self._valid_level_range()
        climatology_dir = self.dependencies['climatology'].work_dir

        # building the mosaic descriptor is the expensive part of plotting a
        # global mesh, so it is built once and shared by every plot
        descriptor = None
        for season in seasons:
            filename = find_climatology_file(climatology_dir, season)
            self.logger.info(f'{season}: {filename}')
            with self.open_model_dataset(filename, config) as ds:
                # the climatological-mean layer geometry, which is what a map
                # at an elevation is a map on
                z_mid, z_interface = get_z_mid_and_interface(ds)
                z_mid = _drop_time(z_mid)
                z_interface = _drop_time(z_interface)
                for field in self.fields:
                    if field == HEAT_CONTENT:
                        descriptor = self._plot_heat_content(
                            ds=ds,
                            season=season,
                            ranges=ranges,
                            z_interface=z_interface,
                            min_level_cell=min_level_cell,
                            max_level_cell=max_level_cell,
                            descriptor=descriptor,
                        )
                        continue
                    if field not in ds:
                        self.logger.info(
                            f'  the simulation did not write {field}, so its '
                            f'maps are skipped'
                        )
                        continue
                    descriptor = self._plot_field(
                        da=ds[field],
                        field=field,
                        season=season,
                        reductions=reductions,
                        z_mid=z_mid,
                        z_interface=z_interface,
                        min_level_cell=min_level_cell,
                        max_level_cell=max_level_cell,
                        descriptor=descriptor,
                    )

    def _mesh_coords(self):
        """
        Get the cell latitudes and longitudes, so that the netCDF beside each
        plot carries the coordinates of what was plotted
        """
        ds = self._read_fields('mesh.nc', ['latCell', 'lonCell'])
        return {name: ds[name] for name in ds.data_vars}

    def _valid_level_range(self):
        """Get the topmost and bottommost valid layer of each column"""
        ds = self._read_fields(
            'vert_coord.nc', ['minLevelCell', 'maxLevelCell']
        )
        return get_valid_level_range(ds)

    def _read_fields(self, filename, fields):
        """
        Read a few named fields from a file of the simulation, translating
        their names but nothing else

        The mesh and the vertical coordinate a simulation names are often
        its initial condition, which carries a full model state.  Opening one
        as a model data set would then derive specific volume from that
        state --- an equation-of-state solve --- to get a handful of fields
        that are already there, so the names are translated and nothing else
        is done.

        Parameters
        ----------
        filename : str
            The local name of the file in the step's work directory

        fields : list of str
            The MPAS-Ocean names of the fields to read; a field the file does
            not have is left out

        Returns
        -------
        ds : xarray.Dataset
            The fields that were there, with MPAS-Ocean names, in memory
        """
        wanted = self.component.map_var_list_to_native_model(fields)
        with xr.open_dataset(self.work_path(filename)) as ds_native:
            present = [name for name in wanted if name in ds_native]
            return self.map_from_native_model_vars(ds_native[present]).load()

    def _plot_heat_content(
        self,
        ds,
        season,
        ranges,
        z_interface,
        min_level_cell,
        max_level_cell,
        descriptor,
    ):
        """
        Derive and plot ocean heat content over each elevation range

        The climatology of temperature and of the layer mass is read once per
        season and every range is a weighted sum over levels of what was
        read, which is negligible beside the read.  That is why the ranges
        are a loop in here rather than an axis the steps are split along.
        """
        config = self.config
        thickness = MASS_THICKNESS_VARIABLES[config.get('ocean', 'model')]
        missing = [
            name for name in ('temperature', thickness) if name not in ds
        ]
        if missing:
            self.logger.info(
                f'  the simulation did not write {", ".join(missing)}, so '
                f'heat content maps are skipped'
            )
            return descriptor

        temperature = _drop_time(ds.temperature)
        layer_mass = _drop_time(get_layer_mass(ds, config))
        specific_heat = get_specific_heat(config)

        for reduction in ranges:
            weights = elevation_range_weights(
                z_interface=z_interface,
                layer_mass=layer_mass,
                min_level_cell=min_level_cell,
                max_level_cell=max_level_cell,
                z_top=reduction.z_top,
                z_bot=reduction.z_bot,
            )
            da_map = heat_content(temperature, weights, specific_heat)
            da_plot = da_map / J_PER_GJ
            da_plot.attrs = dict(da_map.attrs, units='GJ m-2')
            span = reduction.label.replace('_', ' ')
            descriptor = self._plot_map(
                da_map=da_map,
                field=HEAT_CONTENT,
                season=season,
                basename=f'{HEAT_CONTENT}_{season}_{reduction.label}',
                title=f'ocean heat content, {span}, {season}',
                descriptor=descriptor,
                reduction=reduction,
                da_plot=da_plot,
            )
        return descriptor

    def _plot_field(
        self,
        da,
        field,
        season,
        reductions,
        z_mid,
        z_interface,
        min_level_cell,
        max_level_cell,
        descriptor,
    ):
        """Plot one field for one season, at every reduction that applies"""
        da = _drop_time(da)

        if 'nVertLevels' not in da.dims:
            # a field with no vertical dimension is already a map, so there
            # is nothing to reduce and nothing to label it with
            return self._plot_map(
                da_map=da,
                field=field,
                season=season,
                basename=f'{field}_{season}',
                title=f'{field}, {season}',
                descriptor=descriptor,
            )

        for reduction in reductions:
            da_map = apply_vertical_reduction(
                da,
                reduction,
                z_mid=z_mid,
                z_interface=z_interface,
                min_level_cell=min_level_cell,
                max_level_cell=max_level_cell,
            )
            da_map.attrs = dict(da.attrs)
            descriptor = self._plot_map(
                da_map=da_map,
                field=field,
                season=season,
                basename=f'{field}_{season}_{reduction.label}',
                title=f'{field} at {reduction.label}, {season}',
                descriptor=descriptor,
                reduction=reduction,
            )
        return descriptor

    def _plot_map(
        self,
        da_map,
        field,
        season,
        basename,
        title,
        descriptor,
        reduction=None,
        da_plot=None,
    ):
        """
        Write one map to netCDF and plot it, and register both

        ``da_plot`` is what is plotted where that differs from what is
        written, which is how heat content is stored in the unit it means and
        shown in the unit that reads.
        """
        config = self.config
        section = map_section(field)
        if not config.has_section(section):
            raise ValueError(
                f'There is no [{section}] section giving the colormap for '
                f'maps of {field}.  Every field that can be mapped needs '
                f'one; see analysis.cfg.'
            )

        nc_filename = self.work_path(f'{basename}.nc')
        png_filename = self.work_path(f'{basename}.png')
        self._write_netcdf(da_map, field, season, nc_filename, reduction)

        if da_plot is None:
            da_plot = da_map

        simulation_name = config.get('ocean_analysis', 'simulation_name')
        descriptor = plot_global_mpas_field(
            da=da_plot,
            out_filename=png_filename,
            config=config,
            colormap_section=section,
            mesh_filename=self.work_path('mesh.nc'),
            descriptor=descriptor,
            title=f'{simulation_name}: {title}, years {self._range_key()}',
            colorbar_label=da_plot.attrs.get('units', ''),
        )

        # The outputs are registered here rather than in setup() because a
        # field the simulation did not write is skipped, and a step that had
        # declared its plots at setup would fail on the missing files
        # instead.
        for filename in (f'{basename}.nc', f'{basename}.png'):
            self.add_produced_file(filename)
        # a gallery per field, so the landing page shows one thumbnail for
        # each field rather than one for the whole group of maps
        self.add_product(
            plot=f'{basename}.png',
            data=f'{basename}.nc',
            group='climatology_maps',
            gallery=field,
            title=title,
            field=field,
            season=season,
            # the facet is the label, not the reduction itself: a facet is
            # written to the fragment as JSON
            reduction=None if reduction is None else reduction.label,
        )
        self.logger.info(f'  {os.path.basename(png_filename)}')
        return descriptor

    def _write_netcdf(self, da_map, field, season, filename, reduction):
        """Write exactly what was plotted, with what produced it"""
        config = self.config
        ds = xr.Dataset({field: da_map}, coords=self._coords)
        ds = ds.drop_vars('Time', errors='ignore')
        ds.attrs = dict(
            simulation_name=config.get('ocean_analysis', 'simulation_name'),
            field=field,
            season=season,
            vertical_reduction=(
                'none' if reduction is None else reduction.label
            ),
            start_year=self.start_year,
            end_year=self.end_year,
            year_range=self._range_key(),
        )
        if reduction is not None and reduction.kind == 'range':
            # so that a plot cannot be mistaken for a different range
            ds.attrs['elevation_range_top'] = range_bound_label(
                reduction.z_top
            )
            ds.attrs['elevation_range_bottom'] = range_bound_label(
                reduction.z_bot
            )
        write_netcdf(ds=ds, fileName=filename)

    def _range_key(self):
        """The zero-padded range of years, as the work tree spells it"""
        return year_range_key(self.start_year, self.end_year)


def _group_for_field(field):
    """Get the name of the group a field belongs to"""
    for group, group_fields in FIELD_GROUPS.items():
        if field in group_fields:
            return group
    known = sorted(
        field for fields in FIELD_GROUPS.values() for field in fields
    )
    raise ValueError(
        f'The field "{field}" in [ocean_analysis_climatology] fields belongs '
        f'to no field group.  The fields that can be mapped are: '
        f'{", ".join(known)}.'
    )


def _drop_time(da):
    """A climatology holds one time, which is not an axis of a map"""
    if 'Time' in da.dims:
        return da.isel(Time=0)
    return da
