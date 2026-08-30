"""
Reducing the simulation's monthly means one month at a time, inheriting the
months an earlier analysis already reduced.

A product that is a reduction over time -- ocean heat content, and mixed-layer
depth if it is ever computed offline -- costs one pass over three-dimensional
monthly output, which is the expensive thing in the suite and the one thing
worth never doing twice.  Every step is keyed by the range of years it covers,
so extending a twenty-year series to forty is a new step in a new directory;
what makes that cheap is that the new step inherits the twenty years the old
one already reduced and computes only the rest.

Four properties are what make it acceptable for a step to hunt for data on
disk, and each of them is a line of code here:

- **The search scope is what construction guarantees, and nothing wider.**
  Only sibling directories of the same product are candidates: the same step
  class, with the same outputs, differing only in the range.  Nothing outside
  the product's own directory is searched, and no other work directory is ever
  consulted.
- **Admissibility comes from content, not from location.**  Each cache carries
  a provenance stamp -- the identity of the simulation, the options that
  govern the product, and a version integer for the kernel -- and a cache
  whose stamp does not match is recomputed rather than inherited.  The path
  guarantees less than it looks like: a range key says nothing about which
  simulation was analyzed, so the same work directory pointed at a second
  simulation would otherwise cross-contaminate in silence.
- **Only completed steps are candidates.**  A sibling without
  ``polaris_step_complete.log`` is skipped, which also disposes of the
  half-written cache an interrupted run left behind.
- **Reuse is reported.**  Every run says how many months it inherited and from
  where, every candidate it turned down says why, and the stamp travels into
  the cache and into the product beside it.

The step's own cache is the one exception to the completion rule: a partially
written cache in the step's own directory is what a retry starts from, which
is most of what restartability asks for.  It is admitted on its stamp like any
other, since a user who changes an option that governs the product and re-runs
the same range lands on the same directory.
"""

import glob
import os
import re

import xarray as xr

from polaris.tasks.ocean.analysis.analysis_step import AnalysisStep

# What Polaris writes in a step's work directory when the step finishes.  A
# cache in a directory without it was left by a run that was interrupted.
COMPLETION_MARKER = 'polaris_step_complete.log'

# The prefix each entry of the provenance stamp is stored under in the cache
# and in the product beside it, so that ``ncdump -h`` shows what a file was
# computed from and a mismatch can name the entry that differs
STAMP_PREFIX = 'provenance_'

# A sibling directory of the same product is named for the range of years it
# covers, as ``year_range_key`` spells it.  Anything else under the product
# directory was not written by this step class and is not a candidate.
_RANGE_KEY = re.compile(r'\d{4}-\d{4}')


def read_stamp(filename):
    """
    Read the provenance stamp of a cache file

    Parameters
    ----------
    filename : str
        The absolute path to the cache file

    Returns
    -------
    stamp : dict or None
        The stamp, or ``None`` if the file could not be read as one
    """
    try:
        with xr.open_dataset(filename) as ds:
            attrs = dict(ds.attrs)
    except (OSError, ValueError):
        return None
    return {
        key[len(STAMP_PREFIX) :]: str(value)
        for key, value in attrs.items()
        if key.startswith(STAMP_PREFIX)
    }


def stamp_attrs(stamp):
    """
    Get the global attributes a provenance stamp is written to a file as

    The product a step publishes carries the same stamp as the cache behind
    it, so that a plot says what it was computed from without anyone having to
    find the cache.

    Parameters
    ----------
    stamp : dict
        The stamp

    Returns
    -------
    attrs : dict
        The attributes, each prefixed so that reading the stamp back finds
        exactly what was written
    """
    return {f'{STAMP_PREFIX}{key}': value for key, value in stamp.items()}


def stamp_difference(cached, wanted):
    """
    Get the entries of a provenance stamp that keep a cache from being
    inherited

    Parameters
    ----------
    cached : dict or None
        The stamp the cache carries

    wanted : dict
        The stamp the step is asking for

    Returns
    -------
    difference : list of str
        The entries that differ, each as ``key: cached value, not wanted
        value``, empty if the cache may be inherited
    """
    if cached is None:
        return ['the file could not be read']
    difference = []
    for key in sorted(set(cached) | set(wanted)):
        if cached.get(key) != wanted.get(key):
            difference.append(
                f'{key}: {cached.get(key, "absent")}, not '
                f'{wanted.get(key, "absent")}'
            )
    return difference


class Accumulator(AnalysisStep):
    """
    A step that reduces each month of the simulation's monthly means to a few
    numbers, inheriting the months an earlier analysis of the same simulation
    already reduced

    A subclass supplies the kernel, in ``compute_month()``, what else it reads,
    in ``setup_inputs()``, the options that govern its product, in
    ``product_stamp()``, and what to do with the finished series, in
    ``finalize()``.  Everything between those is here.

    Attributes
    ----------
    cache_filename : str
        The local name of the cache of reduced months, which is both this
        step's output and what a later step covering an overlapping range
        inherits from

    kernel_version : int
        The version of the kernel, part of the provenance stamp.  Bump it
        whenever ``compute_month()`` would give a different answer for the
        same month, since that is what keeps a cache computed by older code
        from being inherited by newer code.

    product_dir : str
        The absolute path to the product's directory, the parent of this
        step's own work directory, which is the only place seeds are looked
        for

    stamp : dict
        The provenance stamp a cache has to carry to be inherited

    months : list of tuple
        The ``(year, month, filename)`` of each monthly mean in the range,
        where the filename is the local name of the symlink in the step's
        work directory

    seeds : list of tuple
        The ``(filename, source)`` of each inherited cache, where the filename
        is the local name of the symlink and the source is the path it points
        at

    rejected : list of tuple
        The ``(source, reason)`` of each candidate cache that was turned down
    """

    def __init__(
        self,
        component,
        name,
        subdir,
        start_year,
        end_year,
        cache_filename,
        kernel_version,
        **kwargs,
    ):
        """
        Create an accumulator

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the step belongs to

        name : str
            The name of the step

        subdir : str
            The subdirectory for the step, which ends in the range key

        start_year : int
            The first year of the range this step covers, inclusive

        end_year : int
            The last year of the range this step covers, inclusive

        cache_filename : str
            The local name of the cache of reduced months

        kernel_version : int
            The version of the kernel, part of the provenance stamp

        kwargs
            Keyword arguments passed on to
            :py:class:`polaris.tasks.ocean.analysis.analysis_step.AnalysisStep`
        """
        super().__init__(
            component=component,
            name=name,
            subdir=subdir,
            start_year=start_year,
            end_year=end_year,
            **kwargs,
        )
        self.cache_filename = cache_filename
        self.kernel_version = kernel_version
        self.product_dir = ''
        self.stamp: dict = {}
        self.months: list = []
        self.seeds: list = []
        self.rejected: list = []

    def setup(self):
        """
        Link the monthly means and whatever caches may be inherited

        The seeds are declared as input files like any other input, so that
        the usual provenance and dependency checking apply to what was
        inherited exactly as they do to what was read.
        """
        sim_files = self.get_sim_files()
        self.setup_inputs(sim_files)
        self.months = self._add_monthly_means(sim_files)
        self.stamp = self.provenance_stamp(sim_files)
        # the product's directory is resolved here, once, and as an absolute
        # path: a step must not depend on the process working directory, which
        # is not its own when steps run in parallel
        self.product_dir = os.path.dirname(os.path.abspath(self.work_dir))
        self._discover_seeds()
        self.add_output_file(self.cache_filename)

    def run(self):
        """
        Reduce the months that were not inherited, and hand on the series

        The cache is rewritten as each month is added rather than at the end,
        so that a run that is interrupted leaves a cache its retry can start
        from.  It holds tens of kilobytes, so rewriting it whole is cheaper
        than the bookkeeping an append would need, and it is atomic.
        """
        self.log_inputs()
        self._report_seeds()

        rows = self._inherited_months()
        to_compute = [month for month in self.months if month[:2] not in rows]
        self.logger.info(
            f'inheriting {len(rows)} months, computing {len(to_compute)}'
        )

        # an inherited-only cache is already a cache, and writing it before
        # the loop is what makes the first month computed the only thing a
        # retry can lose
        self._write_cache(rows)
        for year, month, filename in to_compute:
            self.logger.info(f'  {year:04d}-{month:02d}')
            ds_month = self.compute_month(
                self.work_path(filename), year, month
            )
            rows[(year, month)] = _label_month(ds_month, year, month)
            self._write_cache(rows)

        self.finalize(_concatenate(rows))

    def setup_inputs(self, sim_files):
        """
        Link whatever the kernel reads besides the monthly means

        Parameters
        ----------
        sim_files : polaris.tasks.ocean.analysis.sim_files.SimulationFiles
            The files of the simulation being analyzed
        """

    def product_stamp(self):
        """
        Get the config options that govern this product, as a provenance stamp

        These are what a cache has to agree with to be inherited, beyond the
        identity of the simulation and the version of the kernel, which are
        added here.  What belongs in it is whatever would change the numbers:
        an option that only changes how they are labeled or plotted does not,
        since a cache is still a valid cache after it changes.

        Returns
        -------
        stamp : dict
            The options, as strings
        """
        return {}

    def compute_month(self, filename, year, month):
        """
        Reduce one month of the simulation's output

        Parameters
        ----------
        filename : str
            The absolute path to the monthly mean

        year : int
            The simulation year the file covers

        month : int
            The month the file covers

        Returns
        -------
        ds_month : xarray.Dataset
            The reduced month, with no ``Time`` dimension; the accumulator
            adds it along with the year and month
        """
        raise NotImplementedError(
            f'{type(self).__name__} does not define compute_month()'
        )

    def finalize(self, ds):
        """
        Do something with the finished series

        Parameters
        ----------
        ds : xarray.Dataset
            Every month of the range, in order, along a ``Time`` dimension
        """

    def provenance_stamp(self, sim_files):
        """
        Get the provenance stamp a cache has to carry to be inherited

        Parameters
        ----------
        sim_files : polaris.tasks.ocean.analysis.sim_files.SimulationFiles
            The files of the simulation being analyzed

        Returns
        -------
        stamp : dict
            The stamp, as strings
        """
        stamp = {
            # the class is here so that two products that ever shared a
            # directory could not inherit from one another
            'kernel': type(self).__name__,
            'kernel_version': str(self.kernel_version),
            'model': self.config.get('ocean', 'model'),
            # the simulation's own configuration is what the analysis is
            # pointed at, and its output directory is where that resolved to.
            # simulation_name is deliberately not here: it labels plots and
            # does not change a number, so a cache survives renaming a run.
            'simulation': sim_files.omega_config.filename,
            'simulation_path': sim_files.simulation_path,
        }
        stamp.update(self.product_stamp())
        return stamp

    def _add_monthly_means(self, sim_files):
        """Link the monthly means, keeping the date each one covers"""
        months = []
        for sim_file in sim_files.monthly_mean_files(
            self.start_year, self.end_year
        ):
            if sim_file.year is None or sim_file.month is None:
                raise ValueError(
                    f'The monthly mean {sim_file.path} does not say which '
                    f'month it covers, so it cannot be the unit of a cache.  '
                    f'The History stream needs both $Y and $M in its file '
                    f'name.'
                )
            filename = self.add_sim_input_file(sim_file.path)
            months.append((sim_file.year, sim_file.month, filename))
        return months

    def _discover_seeds(self):
        """
        Find the caches under sibling range directories of this product that
        may be inherited from

        Only sibling directories of the same product are looked at, only those
        whose step finished, and only those whose stamp matches.
        """
        self.seeds = []
        self.rejected = []
        if not self.config.getboolean('ocean_analysis', 'reuse_previous'):
            return

        own_dir = os.path.abspath(self.work_dir)
        pattern = os.path.join(self.product_dir, '*', self.cache_filename)
        for source in sorted(glob.glob(pattern)):
            candidate_dir = os.path.dirname(source)
            range_key = os.path.basename(candidate_dir)
            if candidate_dir == own_dir or not _RANGE_KEY.fullmatch(range_key):
                continue
            marker = os.path.join(candidate_dir, COMPLETION_MARKER)
            if not os.path.exists(marker):
                unfinished = (
                    'the step that would have written it did not finish'
                )
                self.rejected.append((source, unfinished))
                continue
            difference = stamp_difference(read_stamp(source), self.stamp)
            if difference:
                self.rejected.append((source, '; '.join(difference)))
                continue
            filename = f'seed_{range_key}.nc'
            self.add_input_file(filename=filename, target=source)
            self.seeds.append((filename, source))

    def _report_seeds(self):
        """Say what may be inherited from and what was turned down"""
        for _, source in self.seeds:
            self.logger.info(f'inheriting from {source}')
        for source, reason in self.rejected:
            self.logger.info(f'not inheriting from {source}: {reason}')

    def _inherited_months(self):
        """
        Get the months of this range that an earlier cache, or this step's
        own partial cache, already holds

        The step's own cache comes first, so that a retry keeps what it
        computed rather than replacing it with an equal answer from a seed.
        """
        rows: dict = {}
        own = self.work_path(self.cache_filename)
        sources = [own] if os.path.exists(own) else []
        sources += [self.work_path(filename) for filename, _ in self.seeds]

        wanted = {(year, month) for year, month, _ in self.months}
        for source in sources:
            difference = stamp_difference(read_stamp(source), self.stamp)
            if difference:
                # a seed's stamp was checked at setup; this catches the step's
                # own cache, written before an option that governs the product
                # was changed and the same range re-run
                self.logger.info(
                    f'not inheriting from {source}: {"; ".join(difference)}'
                )
                continue
            with xr.open_dataset(source) as ds_cache:
                ds = ds_cache.load()
            found = 0
            if 'Time' in ds.dims:
                years = ds.year.values
                months = ds.month.values
                for index, date in enumerate(zip(years, months, strict=True)):
                    key = (int(date[0]), int(date[1]))
                    if key in wanted and key not in rows:
                        rows[key] = ds.isel(Time=[index])
                        found += 1
            self.logger.info(f'  {found} months from {source}')
        return rows

    def _write_cache(self, rows):
        """
        Write the cache, atomically, so that an interrupted run cannot leave
        a file that looks complete
        """
        ds = _concatenate(rows)
        ds.attrs.update(stamp_attrs(self.stamp))
        filename = self.work_path(self.cache_filename)
        partial = f'{filename}.partial'
        unlimited = ['Time'] if 'Time' in ds.dims else []
        ds.to_netcdf(partial, unlimited_dims=unlimited)
        os.replace(partial, filename)


def _label_month(ds_month, year, month):
    """Give a reduced month the year and month it covers, along ``Time``"""
    ds_month = ds_month.expand_dims(dim='Time')
    ds_month['year'] = ('Time', [year])
    ds_month['month'] = ('Time', [month])
    return ds_month


def _concatenate(rows):
    """Put the months in order along ``Time``"""
    if not rows:
        return xr.Dataset()
    return xr.concat([rows[key] for key in sorted(rows)], dim='Time')
