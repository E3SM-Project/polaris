"""
Climatologies of monthly means with ``ncclimo``.

Every climatology the analysis makes is computed the same way, so that they
are comparable with each other and with the ones zppy produces.  A step that
makes one runs :py:func:`run_ncclimo` on the monthly means it linked, and a
step that reads one finds it with :py:func:`find_climatology_file`.
"""

import glob
import os

from mpas_tools.logging import check_call

from polaris.tasks.ocean.analysis.sim_files import check_month_covered

# ``ncclimo`` in background mode runs one process per month, so this is what
# a step that gives it more than one core will start and therefore what it
# declares.  The pool is sized from this number and never from the size of
# the machine.
NCCLIMO_PROCESSES = 12

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


def run_ncclimo(step, variables, seasons):
    """
    Compute the monthly climatologies and some seasons of a step's monthly
    means with ``ncclimo``

    The input files are the step's ``input_filenames``, one per month in
    chronological order from January of ``start_year``, symlinked into its
    work directory.  ``ncclimo`` assigns each file to a month by its position
    in that list.  The climatologies are written to the same directory.

    Parameters
    ----------
    step : polaris.tasks.ocean.analysis.analysis_step.AnalysisStep
        The step computing the climatology.  It runs ``ncclimo`` in parallel
        if it declared more than one core.

    variables : list of str
        The variables to compute the climatology of, as the files name them

    seasons : list of str
        The seasons to compute beside the twelve monthly climatologies, e.g.
        ``['ANN', 'DJF']``

    Raises
    ------
    ValueError
        If a file's time bounds are not the month ``ncclimo`` would take it
        to cover
    """
    for index, filename in enumerate(step.input_filenames):
        check_month_covered(
            step.work_path(filename),
            year=step.start_year + index // 12,
            month=index % 12 + 1,
        )
    check_call(
        _ncclimo_args(step, variables, seasons),
        step.logger,
        env=_ncclimo_env(step),
    )


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
        The work directory of the step that computed the climatology

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


def _ncclimo_args(step, variables, seasons):
    """Build the ``ncclimo`` command line"""
    # ncclimo's background mode runs one process per month.  The count comes
    # from what the step declared it would start, never from the size of the
    # machine, so that a step running beside this one does not find the node
    # oversubscribed.
    threads = step.cpus_per_task
    parallel_mode = 'bck' if threads > 1 else 'nil'
    # The seasonally discontinuous December convention -- every year in the
    # range contributes its own December, so no data outside the range are
    # needed -- used to be selected with "-a sdd".  NCO 5.3.7 dropped that
    # option and made the convention its behavior, so asking for it now only
    # produces a deprecation warning.  The test of this invocation compares
    # DJF against a day-weighted mean of the monthly climatologies, which is
    # what would catch the convention changing back underneath us.
    return [
        'ncclimo',
        '--no_stdin',
        '-4',
        '--clm_md=mth',
        # ncclimo needs a case name to build its output file names from when,
        # as here, the input files are given rather than generated
        '-c',
        step.config.get('ocean_analysis', 'simulation_name'),
        '-p',
        parallel_mode,
        '-j',
        f'{threads}',
        '-v',
        ','.join(variables),
        f'--seasons={",".join(seasons)}',
        '-s',
        f'{step.start_year}',
        '-e',
        f'{step.end_year}',
        # ncclimo resolves the input files it is given against its input
        # directory, so the directory is named once and the files are named
        # relative to it.  Both are the step's own work directory, which is
        # where the monthly means are symlinked.
        '-i',
        step.work_path(),
        '-o',
        step.work_path(),
    ] + list(step.input_filenames)


def _ncclimo_env(step):
    """
    Get the environment to run ``ncclimo`` in, with its scratch space pointed
    at the step's own work directory

    Two climatologies can run at once, so leaving the scratch path to
    ``TMPDIR`` would let them collide on it.
    """
    scratch_dir = step.work_path('ncclimo_scratch')
    os.makedirs(scratch_dir, exist_ok=True)
    env = dict(os.environ)
    env['TMPDIR'] = scratch_dir
    return env
