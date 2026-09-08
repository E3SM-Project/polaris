import glob
import os

import xarray as xr
from mpas_tools.logging import check_call

from polaris.ocean.model.layer_mass import MASS_THICKNESS_VARIABLES
from polaris.tasks.ocean.analysis.analysis_step import AnalysisStep

# ``ncclimo`` in background mode runs one process per month, so this is what
# the step will start and therefore what it declares.  The pool is sized from
# this number and never from the size of the machine.
NCCLIMO_PROCESSES = 12

# The vertical geometry every map that slices at an elevation needs, and that
# the partial layers at a heat content range boundary need.  Both models write
# these and both are translated as usual.
GEOMETRY_VARIABLES = ('zMid', 'zInterface')

# What ocean heat content is derived from, beside the layer mass below.  Heat
# content is a field group of the maps rather than a product a user lists, so
# its inputs are always in the climatology.
HEAT_CONTENT_VARIABLES = ('temperature',)

# The model's mass-like thickness, read under its native name.  This is the
# one variable the analysis deliberately does not translate: Omega's
# ``PseudoThickness`` and MPAS-Ocean's ``layerThickness`` agree on the mass
# per unit area they imply and disagree on the geometry, so renaming one to
# the other would hide the distinction that matters.  The analysis reads Omega
# output only, so this is the Omega spelling.
MASS_THICKNESS_VARIABLE = MASS_THICKNESS_VARIABLES['omega']

# ``ncclimo`` names the twelve monthly climatologies by month number, so a
# user who asks to plot JAN is asking for the file with 01 in its name
SEASON_KEYS = {
    'JAN': '01',
    'FEB': '02',
    'MAR': '03',
    'APR': '04',
    'MAY': '05',
    'JUN': '06',
    'JUL': '07',
    'AUG': '08',
    'SEP': '09',
    'OCT': '10',
    'NOV': '11',
    'DEC': '12',
}


def get_climatology_variables(config):
    """
    Get the variables a climatology is computed for, in MPAS-Ocean names

    The list is the union of the fields requested for maps, the fields ocean
    heat content is derived from, and the vertical geometry.  It is assembled
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
    for variable in HEAT_CONTENT_VARIABLES + GEOMETRY_VARIABLES:
        if variable not in variables:
            variables.append(variable)
    return variables


def find_climatology_file(work_dir, season):
    """
    Find the ``ncclimo`` output file for one season

    ``ncclimo`` names its output ``<caseid>_<season>_<start>_<end>_climo.nc``.
    Steps that read a climatology glob on the season rather than
    reconstructing that pattern, which is robust to what ``ncclimo`` makes of
    the case name and to its naming changing.  The one substitution that has
    to be made is that the twelve monthly climatologies are named by month
    number rather than by ``JAN`` through ``DEC``.

    Parameters
    ----------
    work_dir : str
        The work directory of the climatology step

    season : str
        The season to find, e.g. ``'ANN'`` or ``'JAN'``

    Returns
    -------
    filename : str
        The absolute path to the climatology file

    Raises
    ------
    FileNotFoundError
        If no file for that season is there

    ValueError
        If more than one file matches, which would make the choice arbitrary
    """
    key = SEASON_KEYS.get(season.upper(), season)
    pattern = os.path.join(work_dir, f'*_{key}_*_climo.nc')
    matches = sorted(glob.glob(pattern))
    if not matches:
        raise FileNotFoundError(
            f'No climatology for season {season} in {work_dir}.  The '
            f'climatology step writes the twelve monthly climatologies and '
            f'one file per season in [ocean_analysis_climatology] seasons, '
            f'so check that option against plot_seasons.'
        )
    if len(matches) > 1:
        names = ', '.join(os.path.basename(match) for match in matches)
        raise ValueError(
            f'{len(matches)} climatology files for season {season} in '
            f'{work_dir}: {names}.  Only one is expected, so the choice '
            f'would be arbitrary.'
        )
    return matches[0]


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
        """
        self.log_inputs()
        seasons = self.config.getlist('ocean_analysis_climatology', 'seasons')
        variables = self._native_variables()
        check_call(
            self._ncclimo_args(variables, seasons),
            self.logger,
            env=self._ncclimo_env(),
        )

    def _native_variables(self):
        """
        Get the variables to compute the climatology for, under the names
        they have in the files, dropping the ones the simulation did not write
        """
        variables = get_climatology_variables(self.config)
        native = self.component.map_var_list_to_native_model(variables)
        # the mass-like thickness has no MPAS-Ocean name to be mapped from,
        # so it joins the list already spelled the way the files spell it
        pairs = list(zip(variables, native, strict=True))
        pairs.append((MASS_THICKNESS_VARIABLE, MASS_THICKNESS_VARIABLE))

        written = self._variables_written()
        present = [native for _, native in pairs if native in written]
        missing = [
            f'{polaris} ({native})' if native != polaris else polaris
            for polaris, native in pairs
            if native not in written
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
                'against the contents of the History stream.'
            )
        self.logger.info(f'climatology variables: {", ".join(present)}')
        return present

    def _variables_written(self):
        """Get the names of the variables in the monthly means"""
        filename = self.work_path(self.input_filenames[0])
        with xr.open_dataset(filename, decode_times=False) as ds:
            return set(ds.variables)

    def _ncclimo_args(self, variables, seasons):
        """Build the ``ncclimo`` command line"""
        # ncclimo's background mode runs one process per month.  The count
        # comes from what the step declared it would start, never from the
        # size of the machine, so that a step running beside this one does
        # not find the node oversubscribed.
        threads = self.cpus_per_task
        parallel_mode = 'bck' if threads > 1 else 'nil'
        # The seasonally discontinuous December convention -- every year in
        # the range contributes its own December, so no data outside the
        # range are needed -- used to be selected with "-a sdd".  NCO 5.3.7
        # dropped that option and made the convention its behavior, so asking
        # for it now only produces a deprecation warning.  The test of this
        # invocation compares DJF against a day-weighted mean of the monthly
        # climatologies, which is what would catch the convention changing
        # back underneath us.
        return [
            'ncclimo',
            '--no_stdin',
            '-4',
            '--clm_md=mth',
            # ncclimo needs a case name to build its output file names from
            # when, as here, the input files are given rather than generated
            '-c',
            self.config.get('ocean_analysis', 'simulation_name'),
            '-p',
            parallel_mode,
            '-j',
            f'{threads}',
            '-v',
            ','.join(variables),
            f'--seasons={",".join(seasons)}',
            '-s',
            f'{self.start_year}',
            '-e',
            f'{self.end_year}',
            # ncclimo resolves the input files it is given against its input
            # directory, so the directory is named once and the files are
            # named relative to it.  Both are the step's own work directory,
            # which is where the monthly means are symlinked.
            '-i',
            self.work_path(),
            '-o',
            self.work_path(),
        ] + list(self.input_filenames)

    def _ncclimo_env(self):
        """
        Get the environment to run ``ncclimo`` in, with its scratch space
        pointed at the step's own work directory

        Two climatologies can run at once, so leaving the scratch path to
        ``TMPDIR`` would let them collide on it.
        """
        scratch_dir = self.work_path('ncclimo_scratch')
        os.makedirs(scratch_dir, exist_ok=True)
        env = dict(os.environ)
        env['TMPDIR'] = scratch_dir
        return env
