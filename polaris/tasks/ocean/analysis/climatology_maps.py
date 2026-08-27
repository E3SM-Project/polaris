from polaris.tasks.ocean.analysis.analysis_step import AnalysisStep

# The field groups maps are chunked into.  A group is the unit because things
# computed together belong together: the two velocity components share one
# vector reconstruction, and heat content over several elevation ranges shares
# one set of layer weights.  Heat content reads no field of its own, since it
# is derived from temperature and the layer masses.
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
        The name of the field group this step covers

    fields : list of str
        The fields of that group that were requested
    """

    def __init__(
        self, component, subdir, field_group, fields, start_year, end_year
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

    def setup(self):
        """
        Link the mesh the maps are plotted on
        """
        sim_files = self.get_sim_files()
        self.add_sim_input_file(sim_files.mesh_filename(), 'mesh.nc')

    def run(self):
        """
        Report the fields and inputs; no maps are plotted yet
        """
        self.logger.info(
            f'field group {self.field_group}: '
            f'{", ".join(self.fields) if self.fields else "derived"}'
        )
        self.log_inputs()


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
