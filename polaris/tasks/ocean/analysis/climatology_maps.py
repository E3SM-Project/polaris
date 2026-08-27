import os
from typing import Optional

import xarray as xr
from mpas_tools.io import write_netcdf

from polaris.ocean.vertical.elevation import (
    IMPLEMENTED_KINDS,
    apply_vertical_reduction,
    get_valid_level_range,
    parse_vertical_reduction,
)
from polaris.tasks.ocean.analysis.analysis_step import AnalysisStep
from polaris.tasks.ocean.analysis.climatology import find_climatology_file
from polaris.tasks.ocean.analysis.config_sections import map_section
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
    'heat_content': (),
}

# Heat content is a field group of the maps rather than a product of its own,
# and it is not one of the fields a user lists, so it is always present
DERIVED_FIELD_GROUPS = ('heat_content',)


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
        self._reductions: Optional[list] = None
        self._coords: dict = {}
        self.add_dependency(climatology, name='climatology')

    def setup(self):
        """
        Link the mesh the maps are plotted on and the vertical coordinate

        The vertical coordinate supplies the topmost and bottommost valid
        layer of each column, which the climatology does not carry.
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
        if not self.fields:
            self.logger.info(
                f'The {self.field_group} field group is derived rather than '
                f'read, and deriving it is not implemented yet, so no maps '
                f'are plotted.'
            )
            return

        config = self.config
        seasons = config.getlist('ocean_analysis_climatology', 'plot_seasons')
        self._reductions = None
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
                for field in self.fields:
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
                        min_level_cell=min_level_cell,
                        max_level_cell=max_level_cell,
                        descriptor=descriptor,
                    )

    def _get_reductions(self):
        """
        Get the vertical reductions to plot fields with a vertical dimension
        at, reporting the ones that are not implemented yet

        This is worked out on first use rather than up front so that a group
        with no field that has a vertical dimension does not report anything
        about elevations, which do not apply to it.
        """
        if self._reductions is not None:
            return self._reductions

        reductions = []
        specs = self.config.getlist('ocean_analysis_climatology', 'elevations')
        for spec in specs:
            reduction = parse_vertical_reduction(spec)
            if reduction.kind in IMPLEMENTED_KINDS:
                reductions.append(reduction)
            else:
                self.logger.info(
                    f'  reducing to {reduction.label} needs the vertical '
                    f'geometry, which is not implemented yet, so no maps '
                    f'are plotted there'
                )
        self._reductions = reductions
        return reductions

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

    def _plot_field(
        self,
        da,
        field,
        season,
        min_level_cell,
        max_level_cell,
        descriptor,
    ):
        """Plot one field for one season, at every reduction that applies"""
        if 'Time' in da.dims:
            da = da.isel(Time=0)

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

        for reduction in self._get_reductions():
            da_map = apply_vertical_reduction(
                da,
                reduction,
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
                reduction=reduction.label,
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
    ):
        """Write one map to netCDF and plot it, and register both"""
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

        simulation_name = config.get('ocean_analysis', 'simulation_name')
        descriptor = plot_global_mpas_field(
            da=da_map,
            out_filename=png_filename,
            config=config,
            colormap_section=section,
            mesh_filename=self.work_path('mesh.nc'),
            descriptor=descriptor,
            title=f'{simulation_name}: {title}, years {self._range_key()}',
            colorbar_label=da_map.attrs.get('units', ''),
        )

        # The outputs are registered here rather than in setup() because a
        # field the simulation did not write is skipped, and a step that had
        # declared its plots at setup would fail on the missing files
        # instead.
        for filename in (nc_filename, png_filename):
            self.add_output_file(filename)
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
            vertical_reduction='none' if reduction is None else reduction,
            start_year=self.start_year,
            end_year=self.end_year,
            year_range=self._range_key(),
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
