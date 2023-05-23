import time

import xarray as xr

from polaris.ocean.model import OceanModelStep


class Forward(OceanModelStep):
    """
    A step for performing forward ocean component runs as part of
    the galewsky jet - perturbed test case

    Attributes
    ----------
    resolution : int
        The resolution of the (uniform) mesh in km
    """

    def __init__(self, test_case, resolution):
        """
        Create a new step

        Parameters
        ----------
        test_case : polaris.ocean.tests.galewsky_jet.test_perturbed.TestPerturbed  # noqa: E501
            The test case this step belongs to

        resolution : int
            The resolution of the (uniform) mesh in km
        """
        super().__init__(test_case=test_case,
                         name='forward',
                         subdir='forward',
                         openmp_threads=1)

        self.resolution = resolution

        # make sure output is double precision
        self.add_yaml_file('polaris.ocean.config', 'output.yaml')

        self.add_yaml_file(
            'polaris.ocean.tests.galewsky_jet.test_perturbed',
            'forward.yaml')

        self.add_input_file(filename='initial_state.nc',
                            target='../initial_state/initial_state.nc')
        self.add_input_file(filename='graph.info',
                            target='../base_mesh/graph.info')

        self.add_output_file(filename='output.nc')

    def compute_cell_count(self, at_setup):
        """
        Compute the approximate number of cells in the mesh, used to constrain
        resources

        Parameters
        ----------
        at_setup : bool
            Whether this method is being run during setup of the step, as
            opposed to at runtime

        Returns
        -------
        cell_count : int or None
            The approximate number of cells in the mesh
        """
        if at_setup:
            # use a heuristic based on QU30 (65275 cells) and QU240 (10383
            # cells)
            cell_count = 6e8 / self.resolution**2
        else:
            # get nCells from the input file
            with xr.open_dataset('initial_state.nc') as ds:
                cell_count = ds.sizes['nCells']
        return cell_count

    def dynamic_model_config(self, at_setup):
        """
        Set the model time step from config options at setup and runtime

        Parameters
        ----------
        at_setup : bool
            Whether this method is being run during setup of the step, as
            opposed to at runtime
        """
        super().dynamic_model_config(at_setup=at_setup)

        config = self.config
        # dt is proportional to resolution: default 30 seconds per km
        dt_per_km = config.getfloat('galewsky_jet', 'dt_per_km')

        dt = dt_per_km * self.resolution
        # https://stackoverflow.com/a/1384565/7728169
        dt_str = time.strftime('%H:%M:%S', time.gmtime(dt))

        options = dict(config_dt=dt_str)
        self.add_model_config_options(options)
