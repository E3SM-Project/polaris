import glob

import xarray as xr
from mpas_tools.logging import check_call

from polaris.ocean.model.layer_mass import MASS_THICKNESS_VARIABLES
from polaris.tasks.ocean.analysis.analysis_step import AnalysisStep
from polaris.tasks.ocean.analysis.ncclimo import NCCLIMO_PROCESSES, run_ncclimo
from polaris.tasks.ocean.analysis.sim_files import (
    SimulationFiles,
    time_mean_suffix,
)

# The vertical geometry every map that slices at an elevation needs, and that
# the partial layers at a heat content range boundary need.  Both models write
# these and both are translated as usual.
GEOMETRY_VARIABLES = ('zMid', 'GeomZInterface')

# What ocean heat content is derived from, beside the layer mass below.  Heat
# content is a field group of the maps rather than a product a user lists, so
# its inputs are always in the climatology.
HEAT_CONTENT_VARIABLES = ('temperature',)

# The vector fields Polaris reconstructs at cell centers when the simulation
# did not write their components, keyed by the edge-normal field they are
# reconstructed from.  Reconstruction is linear, so reconstructing from the
# climatology of the edge-normal field gives exactly the climatology of the
# reconstructed components.
VECTOR_RECONSTRUCTIONS = {
    'normalVelocity': ('velocityZonal', 'velocityMeridional'),
}

# The model's mass-like thickness, read under its native name.  This is the
# one variable the analysis deliberately does not translate: Omega's
# ``PseudoThickness`` and MPAS-Ocean's ``layerThickness`` agree on the mass
# per unit area they imply and disagree on the geometry, so renaming one to
# the other would hide the distinction that matters.  The analysis reads Omega
# output only, so this is the Omega spelling.
MASS_THICKNESS_VARIABLE = MASS_THICKNESS_VARIABLES['omega']


def get_climatology_variables(config):
    """
    Get the variables a climatology is computed for, in MPAS-Ocean names

    The list is the union of the fields requested for maps, the fields ocean
    heat content is derived from, the edge-normal field any requested vector
    components can be reconstructed from, and the vertical geometry.  It is
    assembled
    from config options rather than passed in by the steps that read the
    climatology, so that the shared step stays neutral with respect to which
    tasks pulled it in.

    The model's mass-like thickness is not here, because it has no MPAS-Ocean
    name to translate from; it is added under its native name once the rest of
    the list has been mapped into the names the files use.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        The config options for the analysis

    Returns
    -------
    variables : list of str
        The variables, in the order they were requested, with the derived
        ones appended
    """
    variables = list(config.getlist('ocean_analysis_climatology', 'fields'))
    sources = tuple(
        source
        for source, components in VECTOR_RECONSTRUCTIONS.items()
        if any(component in variables for component in components)
    )
    for variable in HEAT_CONTENT_VARIABLES + sources + GEOMETRY_VARIABLES:
        if variable not in variables:
            variables.append(variable)
    return variables


class Climatology(AnalysisStep):
    """
    A step that computes monthly, seasonal and annual climatologies of the
    simulation's monthly-mean output with ``ncclimo``

    The climatology is shared: every field group of ``climatology_maps`` reads
    it, so it runs once for a range no matter how many products want it.
    """

    # the climatology is what the maps are plotted from, not something a
    # reader browses, so it publishes nothing and writes no fragment
    makes_products = False

    def __init__(self, component, subdir, start_year, end_year):
        """
        Create the climatology step

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the step belongs to

        subdir : str
            The subdirectory for the step

        start_year : int
            The first year of the climatology, inclusive

        end_year : int
            The last year of the climatology, inclusive
        """
        super().__init__(
            component=component,
            name='climatology',
            subdir=subdir,
            start_year=start_year,
            end_year=end_year,
            ntasks=1,
            cpus_per_task=NCCLIMO_PROCESSES,
        )

    def setup(self):
        """
        Link the monthly means the climatology is computed from
        """
        sim_files = self.get_sim_files()
        self.add_sim_input_files(
            sim_files.monthly_mean_files(self.start_year, self.end_year)
        )

    def run(self):
        """
        Compute the climatology with ``ncclimo``

        Omega names each field of a monthly mean for the field and the
        period, ``Temperature_TimeMean1Month``, and ``ncclimo`` keeps the
        names it is given, so the suffix is stripped from every file it
        writes.  The climatology then carries each field's own name, which
        is what the rest of Polaris translates and derives from.
        """
        self.log_inputs()
        seasons = self.config.getlist('ocean_analysis_climatology', 'seasons')
        sim_files = SimulationFiles(self.config, log=self.logger.info)
        suffix = time_mean_suffix(sim_files.monthly_mean_stream())
        variables = self._native_variables(suffix)
        run_ncclimo(
            self, [f'{variable}{suffix}' for variable in variables], seasons
        )
        if suffix:
            self._strip_suffix(variables, suffix)

    def _native_variables(self, suffix):
        """
        Get the variables to compute the climatology for, under the names
        the model gives the fields, dropping the ones the simulation did not
        write

        Parameters
        ----------
        suffix : str
            What the files append to each field's name
        """
        variables = get_climatology_variables(self.config)
        native = self.component.map_var_list_to_native_model(variables)
        # the mass-like thickness has no MPAS-Ocean name to be mapped from,
        # so it joins the list already spelled the way the files spell it
        pairs = list(zip(variables, native, strict=True))
        pairs.append((MASS_THICKNESS_VARIABLE, MASS_THICKNESS_VARIABLE))

        written = self._variables_written()
        pairs = _drop_unneeded_for_reconstruction(pairs, written, suffix)
        present = [
            native for _, native in pairs if f'{native}{suffix}' in written
        ]
        missing = [
            f'{polaris} ({native}{suffix})'
            if native != polaris
            else f'{polaris}{suffix}'
            for polaris, native in pairs
            if f'{native}{suffix}' not in written
        ]
        if missing:
            self.logger.info(
                f'The simulation did not write {", ".join(missing)}, so '
                f'these are left out of the climatology and the products '
                f'that need them are skipped.'
            )
        if not present:
            raise ValueError(
                'The simulation wrote none of the variables the analysis '
                'asked for, so there is nothing to compute a climatology '
                'of.  Check the [ocean_analysis_climatology] fields option '
                'against the Fields of the MonthlyAverages analysis group.'
            )
        self.logger.info(f'climatology variables: {", ".join(present)}')
        return present

    def _strip_suffix(self, variables, suffix):
        """Rename the variables of every climatology file in place"""
        args = ['ncrename', '-O', '-h']
        for variable in variables:
            args.extend(['-v', f'{variable}{suffix},{variable}'])
        filenames = sorted(glob.glob(self.work_path('*_climo.nc')))
        for filename in filenames:
            check_call(args + [filename], self.logger)

    def _variables_written(self):
        """Get the names of the variables in the monthly means"""
        filename = self.work_path(self.input_filenames[0])
        with xr.open_dataset(filename, decode_times=False) as ds:
            return set(ds.variables)


def _drop_unneeded_for_reconstruction(pairs, written, suffix):
    """
    Drop the variables a vector reconstruction makes unnecessary

    An edge-normal field is not needed if the simulation wrote every
    component asked for, and a component the simulation did not write is not
    missing if it can be reconstructed from an edge-normal field it did.

    Parameters
    ----------
    pairs : list of tuple of str
        The MPAS-Ocean and native name of each variable

    written : set of str
        The variables in the monthly means

    suffix : str
        What the files append to each field's name

    Returns
    -------
    pairs : list of tuple of str
        The pairs that are still needed
    """
    is_written = {
        polaris: f'{native}{suffix}' in written for polaris, native in pairs
    }
    unneeded = set()
    for source, components in VECTOR_RECONSTRUCTIONS.items():
        if source not in is_written:
            continue
        requested = [c for c in components if c in is_written]
        if all(is_written[c] for c in requested):
            unneeded.add(source)
        elif is_written[source]:
            unneeded.update(c for c in requested if not is_written[c])
    return [
        (polaris, native)
        for polaris, native in pairs
        if polaris not in unneeded
    ]
