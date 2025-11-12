import importlib.resources as imp_res
from typing import Dict, Union

import xarray as xr
from mpas_tools.io import write_netcdf
from ruamel.yaml import YAML

from polaris import Component


class Ocean(Component):
    """
    The collection of all test case for the MPAS-Ocean core

    Attributes
    ----------
    model : str
        The ocean model being used, either 'mpas-ocean' or 'omega'

    mpaso_to_omega_dim_map : dict
        A map from MPAS-Ocean dimension names to their Omega equivalents

    mpaso_to_omega_var_map : dict
        A map from MPAS-Ocean variable names to their Omega equivalents
    """

    def __init__(self):
        """
        Construct the collection of MPAS-Ocean test cases
        """
        super().__init__(name='ocean')
        self.model: Union[None, str] = None
        self.mpaso_to_omega_dim_map: Union[None, Dict[str, str]] = None
        self.mpaso_to_omega_var_map: Union[None, Dict[str, str]] = None

    def configure(self, config):
        """
        Configure the component

        Parameters
        ----------
        config : polaris.config.PolarisConfigParser
            config options to modify
        """
        section = config['ocean']
        model = section.get('model')
        configs = {'mpas-ocean': 'mpas_ocean.cfg', 'omega': 'omega.cfg'}
        if model not in configs:
            raise ValueError(f'Unknown ocean model {model} in config options')

        config.add_from_package('polaris.ocean', configs[model])

        if model == 'omega':
            self._read_var_map()
        self.model = model

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
        model = self.model
        if model == 'omega':
            assert self.mpaso_to_omega_dim_map is not None
            rename = {
                k: v
                for k, v in self.mpaso_to_omega_dim_map.items()
                if k in ds.dims
            }
            assert self.mpaso_to_omega_var_map is not None
            rename_vars = {
                k: v for k, v in self.mpaso_to_omega_var_map.items() if k in ds
            }
            rename.update(rename_vars)
            ds = ds.rename(rename)
        return ds

    def map_var_list_to_native_model(self, var_list):
        """
        If the model is Omega, rename variables from their MPAS-Ocean names to
        the Omega equivalent (appropriate for validation variable lists)

        Parameters
        ----------
        var_list : list of str
            A list of MPAS-Ocean variable names

        Returns
        -------
        renamed_vars : list of str
            The same list with variables renamed as appropriate for the
            ocean model being run
        """
        renamed_vars = var_list
        model = self.model
        if model == 'omega':
            assert self.mpaso_to_omega_var_map is not None
            renamed_vars = [
                v
                for k, v in self.mpaso_to_omega_var_map.items()
                if k in var_list
            ]
        return renamed_vars

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
        ds = self.map_to_native_model_vars(ds)
        write_netcdf(ds=ds, fileName=filename)

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
        model = self.model
        if model == 'omega':
            # switch keys and values in mpaso_to_omega maps to get
            # omega to mpaso maps
            assert self.mpaso_to_omega_dim_map is not None
            rename = {
                k: v
                for v, k in self.mpaso_to_omega_dim_map.items()
                if k in ds.dims
            }
            assert self.mpaso_to_omega_var_map is not None
            rename_vars = {
                k: v for v, k in self.mpaso_to_omega_var_map.items() if k in ds
            }
            rename.update(rename_vars)
            ds = ds.rename(rename)
        return ds

    def map_var_list_from_native_model(self, var_list):
        """
        If the model is Omega, rename variables from their Omega names to
        the MPAS-Ocean equivalent

        Parameters
        ----------
        var_list : list of str
            A list of MPAS-Ocean variable names

        Returns
        -------
        renamed_vars : list of str
            The same list with variables renamed as appropriate for the
            ocean model being run
        """
        renamed_vars = var_list
        model = self.model
        if model == 'omega':
            # switch keys and values in mpaso_to_omega maps to get
            # omega to mpaso maps
            assert self.mpaso_to_omega_var_map is not None
            renamed_vars = [
                v
                for v, k in self.mpaso_to_omega_var_map.items()
                if k in var_list
            ]
        return renamed_vars

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
        ds = xr.open_dataset(filename, **kwargs)
        ds = self.map_from_native_model_vars(ds)
        return ds

    def _read_var_map(self):
        """
        Read the map from MPAS-Ocean to Omega dimension and variable names
        """
        package = 'polaris.ocean.model'
        filename = 'mpaso_to_omega.yaml'
        text = imp_res.files(package).joinpath(filename).read_text()

        yaml_data = YAML(typ='rt')
        nested_dict = yaml_data.load(text)
        self.mpaso_to_omega_dim_map = nested_dict['dimensions']
        self.mpaso_to_omega_var_map = nested_dict['variables']


# create a single module-level instance available to other components
ocean = Ocean()
