from polaris.tasks.ocean.analysis.analysis_step import AnalysisStep


class HeatContentSeries(AnalysisStep):
    """
    A step that reduces each month of the simulation to globally integrated
    ocean heat content over a set of elevation ranges, and plots the series

    Reading a month at a time is what keeps this step's memory footprint
    independent of the length of the record, and it is what makes a month the
    unit that a later run can inherit.
    """

    def __init__(self, component, subdir, start_year, end_year):
        """
        Create the ocean heat content time series step

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
            name='heat_content_series',
            subdir=subdir,
            start_year=start_year,
            end_year=end_year,
            ntasks=1,
            cpus_per_task=1,
        )

    def setup(self):
        """
        Link the monthly means, the mesh and the vertical coordinate

        The mesh supplies the cell areas of the global integral and the
        vertical coordinate the indices of the top and bottom valid layer of
        each column.
        """
        sim_files = self.get_sim_files()
        self.add_sim_input_file(sim_files.mesh_filename(), 'mesh.nc')
        self.add_sim_input_file(
            sim_files.vert_coord_filename(), 'vert_coord.nc'
        )
        self.add_sim_input_files(
            sim_files.monthly_mean_files(self.start_year, self.end_year)
        )

    def run(self):
        """
        Report the monthly means; no heat content is computed yet
        """
        self.log_inputs()
