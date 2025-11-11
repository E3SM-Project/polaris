from polaris import Step
from polaris.tasks.ocean import Ocean


class OceanIOStep(Step):
    """
    A step that writes input and/or output files for Omega or MPAS-Ocean
    """

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
        if not isinstance(self.component, Ocean):
            raise TypeError(
                'component must be an instance of Ocean to map model vars'
            )
        return self.component.map_to_native_model_vars(ds)

    def write_model_dataset(self, ds, filename):
        """
        Write out the given dataset, mapping dimension and variable names from
        MPAS-Ocean to Omega names if appropriate

        Parameters
        ----------
        ds : xarray.Dataset
            A dataset containing MPAS-Ocean variable names

        filename : str
            The path for the NetCDF file to write
        """
        if not isinstance(self.component, Ocean):
            raise TypeError(
                'component must be an instance of Ocean to map model vars'
            )
        self.component.write_model_dataset(ds, filename)

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
        if not isinstance(self.component, Ocean):
            raise TypeError(
                'component must be an instance of Ocean to map model vars'
            )
        return self.component.map_from_native_model_vars(ds)

    def open_model_dataset(self, filename, **kwargs):
        """
        Open the given dataset, mapping variable and dimension names from Omega
        to MPAS-Ocean names if appropriate

        Parameters
        ----------
        filename : str
            The path for the NetCDF file to open

        kwargs
            keyword arguments passed to `xarray.open_dataset()`

        Returns
        -------
        ds : xarray.Dataset
            The dataset with variables named as expected in MPAS-Ocean
        """
        if not isinstance(self.component, Ocean):
            raise TypeError(
                'component must be an instance of Ocean to map model vars'
            )
        return self.component.open_model_dataset(filename, **kwargs)
