from polaris import ModelStep


class Forward(ModelStep):
    """
    A step for staging a mesh for “single column” test cases

    Attributes
    ----------

    """
    def __init__(self, test_case, name='forward'):
        """
        Create the step
        Parameters
        ----------
        test_case : polaris.TestCase
          The test case this step belongs to
        name : str, optional
          The name of the step
        """
        super().__init__(test_case=test_case, name=name,
                         ntasks=1, min_tasks=1, openmp_threads=1)

        self.add_input_file(filename='grid.nc',
                            target='grid_sc_71.35_-156.5.nc',
                            database='domains/domain_sc_71.35_-156.5/')

        for year in range(1948, 2008):
            self.add_input_file(
                filename=f'forcing/atmosphere_forcing_six_hourly.{year}.nc',
                target=f'LYq_six_hourly.{year}.nc',
                database='domains/domain_sc_71.35_-156.5/')

        self.add_input_file(filename='forcing/atmosphere_forcing_monthly.nc',
                            target='LYq_monthly.nc',
                            database='domains/domain_sc_71.35_-156.5/')

        self.add_input_file(filename='forcing/ocean_forcing_monthly.nc',
                            target='oceanmixed_ice_depth_sc_71.35_-156.5.nc',
                            database='domains/domain_sc_71.35_-156.5/')

        self.add_input_file(
            filename='forcing/snicar_optics_5bnd_snow_and_aerosols.nc',
            target='snicar_optics_5bnd_snow_and_aerosols.nc',
            database='domains/domain_sc_71.35_-156.5/')

        self.add_input_file(
            filename='forcing/standard_optics_mpas_seaice.nc',
            target='standard_optics_mpas_seaice.nc',
            database='domains/domain_sc_71.35_-156.5/')

        self.add_namelist_file(
            package='polaris.seaice.tests.single_column',
            namelist='namelist.seaice')

        self.add_streams_file(
            package='polaris.seaice.tests.single_column',
            streams='streams.seaice')
