from polaris.tasks.ocean.analysis.analysis_step import AnalysisStep


class GlobalStatsTimeSeries(AnalysisStep):
    """
    A step that plots time series of the quantities in the simulation's global
    statistics output
    """

    def __init__(self, component, subdir, start_year, end_year):
        """
        Create the global statistics time series step

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the step belongs to

        subdir : str
            The subdirectory for the step

        start_year : int
            The first year of the time series, inclusive

        end_year : int
            The last year of the time series, inclusive
        """
        super().__init__(
            component=component,
            name='global_stats',
            subdir=subdir,
            start_year=start_year,
            end_year=end_year,
            ntasks=1,
            cpus_per_task=1,
        )

    def setup(self):
        """
        Link the simulation's global statistics output
        """
        sim_files = self.get_sim_files()
        self.add_sim_input_files(
            sim_files.global_stats_files(self.start_year, self.end_year)
        )

    def run(self):
        """
        Report the statistics files; no time series are plotted yet
        """
        self.log_inputs()
