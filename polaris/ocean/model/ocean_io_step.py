import importlib.resources as imp_res
from typing import Dict, Union

import xarray as xr
from mpas_tools.io import write_netcdf
from ruamel.yaml import YAML

from polaris import Step


class OceanIOStep(Step):
    """
    A step that writes input and/or output files for Omega or MPAS-Ocean

    Attributes
    ----------
    mpaso_to_omega_var_map : dict
        A map from MPAS-Ocean variable names to their Omega equivalents

    omega_to_mpaso_var_map : dict
        A map from Omega variable names to their MPAS-Ocean equivalents, the
        inverse of ``mpaso_to_omega_var_map``
    """
    def __init__(self, component, name, **kwargs):
        """
        Create a new step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        name : str
            the name of the task

        kwargs
            keyword arguments passed to `polaris.Step()`
        """
        super().__init__(
            component=component, name=name, **kwargs)

        self.mpaso_to_omega_var_map: Union[None, Dict[str, str]] = None
        self.omega_to_mpaso_var_map: Union[None, Dict[str, str]] = None

    def setup(self):
        """
        If the ocean model is Omega, set up maps between Omega and MPAS-Ocean
        variable names
        """
        config = self.config
        model = config.get('ocean', 'model')
        if model == 'omega':
            self._read_var_map()
        elif model != 'mpas-ocean':
            raise ValueError(f'Unexpected ocean model: {model}')
        super().setup()

    def map_to_native_model_vars(self, ds):
        """
        If the model is Omega, rename variables in a dataset from their
        MPAS-Ocean names to the Omega equivalent (appropriate for input
        datasets like an initial condition)

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
        config = self.config
        model = config.get('ocean', 'model')
        if model == 'omega':
            assert self.mpaso_to_omega_var_map is not None
            ds = ds.rename(self.mpaso_to_omega_var_map)
        return ds

    def write_model_dataset(self, ds, filename):
        """
        Write out the given dataset, mapping variable names from MPAS-Ocean
        to Omega names if appropriate

        Parameters
        ----------
        ds : xarray.Dataset
            A dataset containing MPAS-Ocean variable names

        filename : str
            The path for the NetCDF file to write
        """
        ds = self.map_to_native_model_vars(ds)
        write_netcdf(ds=ds, fileName=filename)

    def map_from_native_model_vars(self, ds):
        """
        If the model is Omega, rename variables in a dataset from their
        Omega names to the MPAS-Ocean equivalent (appropriate for datasets
        that are output from the model)

        Parameters
        ----------
        ds : xarray.Dataset
            A dataset containing variable names native to either ocean model

        Returns
        -------
        ds : xarray.Dataset
            The same dataset with variables named as expected in MPAS-Ocean
        """
        config = self.config
        model = config.get('ocean', 'model')
        if model == 'omega':
            assert self.omega_to_mpaso_var_map is not None
            ds = ds.rename(self.omega_to_mpaso_var_map)
        return ds

    def open_model_dataset(self, filename):
        """
        Open the given dataset, mapping variable names from Omega to MPAS-Ocean
        names if appropriate

        Parameters
        ----------
        filename : str
            The path for the NetCDF file to open

        Returns
        -------
        ds : xarray.Dataset
            The dataset with variables named as expected in MPAS-Ocean
        """
        ds = xr.open_dataset(filename)
        ds = self.map_from_native_model_vars(ds)
        return ds

    def _read_var_map(self):
        """
        Read the map from MPAS-Ocean to Omega config options
        """
        package = 'polaris.ocean.model'
        filename = 'mpaso_to_omega.yaml'
        text = imp_res.files(package).joinpath(filename).read_text()

        yaml_data = YAML(typ='rt')
        nested_dict = yaml_data.load(text)
        self.mpaso_to_omega_var_map = nested_dict['variables']
        assert self.mpaso_to_omega_var_map is not None
        self.omega_to_mpaso_var_map = {
            v: k for k, v in self.mpaso_to_omega_var_map.items()}
