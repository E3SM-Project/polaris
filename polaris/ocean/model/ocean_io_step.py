from typing import TYPE_CHECKING

from polaris import Step

if TYPE_CHECKING:
    # Keep Ocean as a type-only import. Importing it at runtime pulls
    # polaris.tasks.ocean back into polaris.ocean.model while that package is
    # still importing these step classes, creating a circular import.
    from polaris.tasks.ocean import Ocean


class OceanIOStep(Step):
    """
    A step that writes input and/or output files for Omega or MPAS-Ocean
    """

    # make sure component is of type Ocean, using a string to avoid circular
    # imports
    component: 'Ocean'

    def __init__(self, component: 'Ocean', **kwargs):
        super().__init__(component=component, **kwargs)

    def map_to_native_model_vars(self, ds):
        """
        If the model is Omega, rename dimensions and variables in a dataset
        from their MPAS-Ocean names to the Omega equivalent (appropriate for
        input datasets like an initial condition)

        Parameters
        ----------
        ds : xarray.Dataset
            A dataset containing MPAS-Ocean variable names

        Returns
        -------
        ds : xarray.Dataset
            The same dataset with variables renamed as appropriate for the
            ocean model being run
        """
        return self.component.map_to_native_model_vars(ds)

    def write_model_dataset(self, ds, filename, config):
        """
        Write out the given dataset, mapping dimension and variable names from
        MPAS-Ocean to Omega names if appropriate

        Parameters
        ----------
        ds : xarray.Dataset
            A dataset containing MPAS-Ocean variable names

        filename : str
            The path for the NetCDF file to write

        config : polaris.config.PolarisConfigParser
            Configuration for the task; forwarded to the Ocean component.
        """
        self.component.write_model_dataset(ds, filename, config=config)

    def write_initial_state_dataset(self, ds, filename, config):
        """
        Write an initial-state dataset, omitting horizontal mesh fields and
        (for Omega) vertical coordinate fields.

        Parameters
        ----------
        ds : xarray.Dataset
            A dataset containing MPAS-Ocean variable names

        filename : str
            The path for the NetCDF file to write

        config : polaris.config.PolarisConfigParser
            Configuration for the task; forwarded to the Ocean component.
        """
        self.component.write_initial_state_dataset(ds, filename, config)

    def write_vert_coord_dataset(self, ds, filename, config):
        """
        Write a vertical-coordinate dataset for Omega's ``InitialVertCoord``
        stream.  No-op for MPAS-Ocean.

        Parameters
        ----------
        ds : xarray.Dataset
            A dataset containing MPAS-Ocean variable names

        filename : str
            The path for the NetCDF file to write

        config : polaris.config.PolarisConfigParser
            Configuration for the task; forwarded to the Ocean component.
        """
        self.component.write_vert_coord_dataset(ds, filename, config)

    def map_from_native_model_vars(self, ds):
        """
        If the model is Omega, rename dimensions and variables in a dataset
        from their Omega names to the MPAS-Ocean equivalent (appropriate for
        datasets that are output from the model)

        Parameters
        ----------
        ds : xarray.Dataset
            A dataset containing variable names native to either ocean model

        Returns
        -------
        ds : xarray.Dataset
            The same dataset with variables named as expected in MPAS-Ocean
        """
        return self.component.map_from_native_model_vars(ds)

    def open_model_dataset(self, filename, config, **kwargs):
        """
        Open the given dataset, mapping variable and dimension names from Omega
        to MPAS-Ocean names if appropriate

        Parameters
        ----------
        filename : str
            The path for the NetCDF file to open

        config : polaris.config.PolarisConfigParser
            Configuration for the task; forwarded to the Ocean component.

        kwargs
            keyword arguments passed to `xarray.open_dataset()`

        Returns
        -------
        ds : xarray.Dataset
            The dataset with variables named as expected in MPAS-Ocean
        """
        return self.component.open_model_dataset(
            filename, config=config, **kwargs
        )
