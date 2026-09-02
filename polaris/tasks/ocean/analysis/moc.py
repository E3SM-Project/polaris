from polaris.tasks.ocean.analysis.analysis_step import AnalysisStep


class Moc(AnalysisStep):
    """
    A step that time averages the meridional overturning circulation Omega
    computes in situ and plots it against latitude and elevation

    Attributes
    ----------
    has_moc_output : bool
        Whether the simulation wrote MOC output at all
    """

    def __init__(self, component, subdir, start_year, end_year):
        """
        Create the MOC step

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the step belongs to

        subdir : str
            The subdirectory for the step

        start_year : int
            The first year to average over, inclusive

        end_year : int
            The last year to average over, inclusive
        """
        super().__init__(
            component=component,
            name='moc',
            subdir=subdir,
            start_year=start_year,
            end_year=end_year,
            ntasks=1,
            cpus_per_task=1,
        )
        self.has_moc_output = False

    def setup(self):
        """
        Link the simulation's MOC output, if it wrote any

        Omega's MOC diagnostic is new, so users will analyze simulations that
        predate it.  That is reported rather than treated as a failure, and
        the step goes on to produce nothing.
        """
        sim_files = self.get_sim_files()
        moc_files = sim_files.moc_files(self.start_year, self.end_year)
        self.has_moc_output = moc_files is not None
        if moc_files is not None:
            self.add_sim_input_files(moc_files)

    def run(self):
        """
        Report the MOC output; no plot is made yet
        """
        if not self.has_moc_output:
            self.logger.info(
                'The simulation wrote no MOC output, so there is nothing to '
                'plot.'
            )
            return
        self.log_inputs()
