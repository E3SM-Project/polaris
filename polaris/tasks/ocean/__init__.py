import importlib.resources as imp_res
import os
from typing import Dict, Tuple, Union

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
        The ocean model being used, either 'mpas-ocean', 'omega', or
        'unknown' if no OceanModelStep or OceanIOStep is present in any task

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

    def configure(self, config, tasks):
        """
        Configure the component

        Parameters
        ----------
        config : polaris.config.PolarisConfigParser
            config options to modify

        tasks : list of polaris.Task
            The tasks to be set up for this component
        """
        section = config['ocean']
        model = section.get('model')
        has_ocean_io_steps, has_ocean_model_steps = (
            self._has_ocean_io_model_steps(tasks)
        )
        if not (has_ocean_model_steps or has_ocean_io_steps):
            # No ocean I/O or model steps, so no model detection or build
            # needed.
            if model == 'detect':
                model = 'unknown'
            self.model = model
            return

        if model == 'detect':
            model = self._detect_model(config)
            print('Detected ocean model:', model)
            config.set('ocean', 'model', model)

        configs = {'mpas-ocean': 'mpas_ocean.cfg', 'omega': 'omega.cfg'}

        if model not in configs:
            raise ValueError(f'Unknown ocean model {model}')

        config.add_from_package('polaris.ocean', configs[model])

        component_path = config.get('paths', 'component_path')
        if has_ocean_model_steps:
            # we need to try to detect the model and build it if needed
            if model == 'omega':
                detected = self._detect_omega_build(component_path)
            else:
                detected = self._detect_mpas_ocean_build(component_path)

            if not detected:
                # looks like we need to build the model
                build = config.getboolean('build', 'build')
                if not build:
                    print(
                        f'Ocean model {model} not found in '
                        f'{component_path}, setting build option to True'
                    )
                    config.set('build', 'build', 'True', user=True)

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

    def _has_ocean_io_model_steps(self, tasks) -> Tuple[bool, bool]:
        """
        Determine if any steps in this component descend from OceanIOStep or
        OceanModelStep
        """
        # local import to avoid circular imports
        from polaris.ocean.model.ocean_io_step import OceanIOStep
        from polaris.ocean.model.ocean_model_step import OceanModelStep

        has_ocean_model_steps = any(
            isinstance(step, OceanModelStep)
            for task in tasks
            for step in task.steps.values()
        )
        has_ocean_io_steps = any(
            isinstance(step, OceanIOStep)
            for task in tasks
            for step in task.steps.values()
        )

        return has_ocean_io_steps, has_ocean_model_steps

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

    def _detect_model(self, config) -> str:
        """
        Detect which ocean model to use
        """
        # build config options for each model, so the default component_path
        # can be read if it hasn't been overridden
        omega_config = config.copy()
        omega_config.add_from_package('polaris.ocean', 'omega.cfg')
        omega_path = omega_config.get('paths', 'component_path')

        mpas_ocean_config = config.copy()
        mpas_ocean_config.add_from_package('polaris.ocean', 'mpas_ocean.cfg')
        mpas_ocean_path = mpas_ocean_config.get('paths', 'component_path')

        if self._detect_omega_build(omega_path):
            return 'omega'
        elif self._detect_mpas_ocean_build(mpas_ocean_path):
            return 'mpas-ocean'
        else:
            raise ValueError(
                f'Could not detect ocean model; neither MPAS-Ocean '
                f'nor Omega appear to be available; '
                f'searched {omega_path} and {mpas_ocean_path}.'
            )

    def _detect_omega_build(self, path) -> bool:
        """
        Detect if Omega is available
        """
        required_files = [
            'configs/Default.yml',
            'src/omega.exe',
        ]
        path = os.path.abspath(path)

        all_found = True
        for required_file in required_files:
            if not os.path.exists(os.path.join(path, required_file)):
                all_found = False
                break
        return all_found

    def _detect_mpas_ocean_build(self, path) -> bool:
        """
        Detect if MPAS-Ocean is available

        Returns
        -------
        is_mpas_ocean : bool
            True if MPAS-Ocean appears to be available, False otherwise
        """
        required_files = [
            'default_inputs/namelist.ocean.forward',
            'default_inputs/streams.ocean.forward',
            'src/Registry_processed.xml',
            'ocean_model',
        ]
        path = os.path.abspath(path)

        all_found = True
        for required_file in required_files:
            if not os.path.exists(os.path.join(path, required_file)):
                all_found = False
                break
        return all_found


# create a single module-level instance available to other components
ocean = Ocean()
