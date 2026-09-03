from polaris.tasks.ocean.analysis.analysis_step import AnalysisStep

# ``ncclimo`` in background mode runs one process per month, so this is what
# the step will start and therefore what it declares.  The pool is sized from
# this number and never from the size of the machine.
NCCLIMO_PROCESSES = 12


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
        Report the monthly means; the climatology itself is not computed yet
        """
        self.log_inputs()
