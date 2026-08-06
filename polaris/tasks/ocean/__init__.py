import importlib.resources as imp_res
import os
from typing import Dict, Literal, Tuple, Union

import numpy as np
import xarray as xr
from mpas_tools.io import open_dataset, write_netcdf
from mpas_tools.vector.reconstruct import reconstruct_variable
from ruamel.yaml import YAML

from polaris import Component
from polaris.constants import get_constant
from polaris.mesh.reconstruct import (
    cartesian_to_local_geographic,
    tangential_reconstruction,
)
from polaris.ocean.eos import convert_tracers
from polaris.ocean.init_state import pressure_for_tracer_conversion
from polaris.ocean.surface_pressure import surface_pressure_from_config
from polaris.ocean.vertical.diagnostics import (
    geom_thickness_from_ds,
    pseudothickness_from_ds,
)
from polaris.ocean.vertical.ztilde import (
    geom_height_from_pseudo_height,
    get_iter_count_for_eos,
    pressure_and_spec_vol_from_state_at_geom_height,
)

RhoSw = get_constant('seawater_density_reference')


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

    horiz_mesh_vars : list of str
        Variables that belong in the horizontal mesh file rather than the
        initial condition file

    vert_coord_vars : list of str
        Variables that belong in the vertical coordinate file (Omega only)
        rather than the initial condition file
    """

    def __init__(self):
        """
        Construct the collection of MPAS-Ocean test cases
        """
        super().__init__(name='ocean')
        self.model: Union[None, str] = None
        self.mpaso_to_omega_dim_map: Union[None, Dict[str, str]] = None
        self.mpaso_to_omega_var_map: Union[None, Dict[str, str]] = None
        self.horiz_mesh_vars: Union[None, list[str]] = None
        self.vert_coord_vars: Union[None, list[str]] = None
        self.state_vars: Union[None, list[str]] = None

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

        self.model = model
        if model == 'omega':
            self._read_var_map()

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
                self.mpaso_to_omega_var_map.get(v, v) for v in var_list
            ]
        return renamed_vars

    def write_model_dataset(self, ds, filename, config, contains_state=False):
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
            Configuration for the task; used when the model is Omega to
            convert geometric layer thickness to pseudo-thickness before
            writing.

        contains_state : bool, optional
            If True, perform additional validation that all configured state
            variables are present in the dataset after mapping.
        """
        if self.model == 'omega':
            # fields to be converted from geometric to pseudo thickness
            mpas_to_omega_vars = {
                'layerThickness': 'PseudoThickness',
                'restingThickness': 'RefPseudoThickness',
                'vertAleTransportTop': 'TotalVerticalPseudoVelocity',
                'vertVelocityTop': 'VerticalPseudoVelocity',
            }
            for mpas_var, omega_var in mpas_to_omega_vars.items():
                if mpas_var in ds.keys() and omega_var not in ds.keys():
                    if mpas_var in ['layerThickness', 'restingThickness']:
                        pseudothickness, spec_vol = pseudothickness_from_ds(
                            ds, config=config, src_var_name=mpas_var
                        )
                        if (
                            pseudothickness is not None
                            and spec_vol is not None
                        ):
                            ds[omega_var] = pseudothickness
                            if (
                                'SpecVol' not in ds.keys()
                                and mpas_var == 'layerThickness'
                            ):
                                ds['SpecVol'] = spec_vol
                    elif mpas_var in [
                        'vertVelocityTop',
                        'vertAleTransportTop',
                    ]:
                        if (
                            'SpecVol' not in ds.keys()
                            and 'layerThickness' in ds.keys()
                        ):
                            _, spec_vol = pseudothickness_from_ds(
                                ds,
                                config=config,
                                src_var_name='layerThickness',
                            )
                            ds[omega_var] = ds[mpas_var] / (spec_vol * RhoSw)

        ds = self.map_to_native_model_vars(ds)

        if contains_state:
            # After map_to_native_model_vars, the dataset contains
            # LayerThickness and PseudoThickness which are both
            # pseudo-thickness
            if self.state_vars is None:
                self._read_variables_yaml()
            if self.model == 'omega' and self.mpaso_to_omega_var_map is None:
                self._read_var_map()
            assert self.state_vars is not None

            native_vars = self.map_var_list_to_native_model(self.state_vars)
            self._check_vars_present(ds, native_vars, 'write_model_dataset')

        write_netcdf(ds=ds, fileName=filename)

    def write_horiz_mesh_dataset(self, ds, filename, config):
        """
        Write a horizontal mesh dataset, validating that all expected mesh
        variables are present.

        For Omega, the vector-reconstruction stencil and weight fields
        (produced alongside the base mesh by
        ``polaris.mesh.spherical.SphericalBaseStep``) are merged in from
        ``reconstruction_weights.nc`` in the current working directory, since
        MPAS-Ocean does not support least-squares vector reconstruction.

        Parameters
        ----------
        ds : xarray.Dataset
            A dataset containing MPAS-Ocean or native model variable names
            including all horizontal mesh variables

        filename : str
            The path for the NetCDF file to write

        config : polaris.config.PolarisConfigParser
            Not used; retained for API compatibility.
        """
        if self.horiz_mesh_vars is None:
            self._read_variables_yaml()
        if self.model == 'omega' and self.mpaso_to_omega_var_map is None:
            self._read_var_map()
        assert self.horiz_mesh_vars is not None
        if self.model == 'omega':
            recon_filename = 'reconstruction_weights.nc'
            if not os.path.exists(recon_filename):
                raise FileNotFoundError(
                    f'{recon_filename} not found but is required to write '
                    'the horizontal mesh dataset for Omega. Make sure the '
                    'base mesh step ran with vector-reconstruction weight '
                    'generation enabled and that it is added as an input '
                    'file to this step.'
                )
            ds_recon = open_dataset(recon_filename)
            ds = ds.merge(ds_recon)
        ds = self.map_to_native_model_vars(ds)
        native_vars = self.map_var_list_to_native_model(self.horiz_mesh_vars)
        self._check_vars_present(ds, native_vars, 'write_horiz_mesh_dataset')
        write_netcdf(ds=ds, fileName=filename)

    def remove_horiz_mesh_vars(self, ds):
        """
        Remove horizontal mesh variables from a dataset.

        Parameters
        ----------
        ds : xarray.Dataset
            A dataset containing MPAS-Ocean variable names

        Returns
        -------
        ds : xarray.Dataset
            The same dataset without horizontal mesh variables
        """
        if self.horiz_mesh_vars is None:
            self._read_variables_yaml()

        assert self.horiz_mesh_vars is not None
        drop = [v for v in self.horiz_mesh_vars if v in ds]
        if drop:
            ds = ds.drop_vars(drop)
        return ds

    def write_vert_coord_dataset(self, ds, filename, config):
        """
        Write a vertical-coordinate dataset for Omega's ``InitialVertCoord``
        stream.  This is a no-op for MPAS-Ocean (vertical coordinate fields
        stay in the initial state file).

        Parameters
        ----------
        ds : xarray.Dataset
            A dataset containing MPAS-Ocean or native model variable names,
            including the vertical coordinate variables and the
            temperature/salinity/ssh fields needed for pseudo-thickness
            conversion.

        filename : str
            The path for the NetCDF file to write

        config : polaris.config.PolarisConfigParser
            Configuration for the task; used when converting
            ``restingThickness`` to ``RefPseudoThickness``.
        """
        if self.vert_coord_vars is None:
            self._read_variables_yaml()
        if self.model == 'omega' and self.mpaso_to_omega_var_map is None:
            self._read_var_map()
        assert self.vert_coord_vars is not None

        native_vars = self.map_var_list_to_native_model(self.vert_coord_vars)
        if self.model != 'omega':
            self._check_vars_present(
                ds, native_vars, 'write_vert_coord_dataset'
            )
            return

        ds_vc = ds.copy()

        # Convert restingThickness (geometric) to RefPseudoThickness (pseudo).
        # Resting thicknesses are defined at zero surface pressure, so the
        # conversion must not use whatever surface pressure the dataset
        # happens to carry.
        if 'restingThickness' in ds_vc and 'RefPseudoThickness' not in ds_vc:
            pseudothickness, _ = pseudothickness_from_ds(
                ds_vc,
                config=config,
                src_var_name='restingThickness',
                surf_pressure=0.0,
            )
            if pseudothickness is not None:
                # VertCoordInit stream is time-independent; drop Time dim
                if 'Time' in pseudothickness.dims:
                    pseudothickness = pseudothickness.isel(Time=0)
                ds_vc['RefPseudoThickness'] = pseudothickness
        if 'vertCoordMovementWeights' not in ds_vc:
            print(
                'vertCoordMovementWeights not found in vert_coord dataset; '
                'defaulting to ones'
            )
            ds_vc['vertCoordMovementWeights'] = xr.DataArray(
                data=np.ones(
                    (1, ds_vc.sizes['nVertLevels'], ds_vc.sizes['nCells']),
                    dtype=float,
                ),
                dims=['Time', 'nVertLevels', 'nCells'],
                attrs={
                    'units': '',
                    'long_name': 'Vertical coordinate movement weights',
                },
            )

        ds_vc = self.map_to_native_model_vars(ds_vc)
        self._check_vars_present(
            ds_vc, native_vars, 'write_vert_coord_dataset'
        )
        ds_vc = ds_vc[native_vars]
        write_netcdf(ds=ds_vc, fileName=filename)

    def remove_vert_coord_vars(self, ds):
        """
        Remove vertical coordinate variables from a dataset.

        Parameters
        ----------
        ds : xarray.Dataset
            A dataset containing MPAS-Ocean variable names

        Returns
        -------
        ds : xarray.Dataset
            The same dataset without vertical coordinate variables
        """
        if self.vert_coord_vars is None:
            self._read_variables_yaml()

        assert self.vert_coord_vars is not None
        drop = [v for v in self.vert_coord_vars if v in ds]
        if drop:
            ds = ds.drop_vars(drop)
        return ds

    def write_initial_state_dataset(
        self,
        ds,
        filename,
        config,
        tracer_convention=None,
        lon=None,
        lat=None,
        logger=None,
    ):
        """
        Write an initial-state dataset, converting the tracers to the
        convention the model expects and omitting horizontal mesh fields and
        (for Omega) vertical coordinate fields.

        For MPAS-Ocean the vertical coordinate variables remain in the initial
        state file.  For Omega they are written separately via
        :py:meth:`write_vert_coord_dataset`.

        Parameters
        ----------
        ds : xarray.Dataset
            A dataset containing MPAS-Ocean variable names.  Its tracers are
            converted on a copy, so they are left untouched.

        filename : str
            The path for the NetCDF file to write

        config : polaris.config.PolarisConfigParser
            Configuration for the task; forwarded to
            :py:meth:`write_model_dataset`.

        tracer_convention : {'teos-10', 'mpas-ocean'}, optional
            The convention of ``temperature`` and ``salinity`` in ``ds``.  The
            default is to assume the convention implied by the ``eos_type``
            config option: ``'teos-10'`` for the TEOS-10 equation of state and
            no conversion otherwise.

        lon : float or xarray.DataArray, optional
            The longitude(s) in degrees at which to convert tracers, if not
            the location implied by the mesh (see
            :ref:`dev-ocean-framework-init-state`)

        lat : float or xarray.DataArray, optional
            The latitude(s) in degrees at which to convert tracers, as for
            ``lon``

        logger : logging.Logger, optional
            A logger for logging EOS iteration information if a pressure needs
            to be computed for the tracer conversion
        """
        if self.model is None:
            self.model = config.get('ocean', 'model')
        ds = self._convert_tracers_for_model(
            ds,
            config,
            tracer_convention=tracer_convention,
            lon=lon,
            lat=lat,
            logger=logger,
        )
        if 'pressure' in ds:
            # pressure is a diagnostic that neither model reads, and it is
            # only present for some vertical coordinates, so drop it to keep
            # initial conditions consistent with one another
            ds = ds.drop_vars('pressure')
        ds = self.remove_horiz_mesh_vars(ds)
        if self.model == 'omega':
            ds = self.remove_vert_coord_vars(ds)
            # Omega requires a surface pressure in its initial state but
            # MPAS-Ocean does not, so only add it for Omega.  This is the one
            # place the vertical_grid:surface_pressure config option is read
            # (it always has a value from ocean.cfg); tasks that prescribe
            # their own surface pressure are left untouched.
            if 'SurfacePressure' not in ds.keys():
                ds['SurfacePressure'] = surface_pressure_from_config(
                    config, ds.sizes['nCells']
                )

        self.write_model_dataset(ds, filename, config, contains_state=True)

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

    def open_model_dataset(
        self,
        filename,
        config,
        mesh_filename=None,
        vert_filename=None,
        reconstruct_variables=None,
        coeffs_filename=None,
        reconstruct_method: Literal['RBF', 'LSTSQ'] = 'LSTSQ',
        tracer_convention=None,
        lon=None,
        lat=None,
        logger=None,
        **kwargs,
    ):
        """
        Open the given dataset, mapping variable and dimension names from Omega
        to MPAS-Ocean names if appropriate

        Parameters
        ----------
        filename : str
            The path for the NetCDF file to open

        config : polaris.config.PolarisConfigParser
            Configuration for the task; used when the model is Omega to
            compute geometric layer thickness from pseudo-thickness.

        mesh_filename : str, optional
            Path to the mesh NetCDF file. Should contain the reconstruction
            weights if using the LSTSQ reconstruction method.  It is also
            where the locations needed for a tracer conversion come from.

        reconstruct_variables : list of str, optional
            List of variable names to reconstruct in the dataset.

        coeffs_filename : str, optional
            Path to the coefficients NetCDF file.

        reonstruct_method : {'RBF', 'LSTSQ'}, optional
            Method to use for reconstructing vector variables.
            RBF: Radial Basis Function; approach used in MPAS-Ocean.
            LSTSQ: Least-squares reconstruction; new approach in Omega

        tracer_convention : {'teos-10', 'mpas-ocean'}, optional
            The convention of ``temperature`` and ``salinity`` in the dataset
            that is returned.  The default is to leave the tracers in the
            convention the ocean model wrote them in: ``'teos-10'``
            (conservative temperature and absolute salinity) for Omega and
            ``'mpas-ocean'`` (potential temperature and practical salinity)
            for MPAS-Ocean.  The two conventions are indistinguishable unless
            the ``eos_type`` config option is ``teos-10``, so this is a no-op
            for any other equation of state.

        lon : float or xarray.DataArray, optional
            The longitude(s) in degrees at which to convert tracers, if not
            the location implied by the mesh

        lat : float or xarray.DataArray, optional
            The latitude(s) in degrees at which to convert tracers, as for
            ``lon``

        logger : logging.Logger, optional
            A logger for logging EOS iteration information if a pressure needs
            to be computed for the tracer conversion

        kwargs
            keyword arguments passed to `xarray.open_dataset()`

        Returns
        -------
        ds : xarray.Dataset
            The dataset with variables named as expected in MPAS-Ocean
        """
        ds = open_dataset(filename, **kwargs)
        if self.model == 'omega' and 'GeomLayerThickness' in ds.keys():
            # this is an indication that the geometric layer thickness is
            # derived from MPAS-O datasets or python since Omega does not
            # compute it
            ds['layerThickness'] = ds.GeomLayerThickness
        if (
            self.model == 'omega'
            and 'layerThickness' not in ds.keys()
            and 'PseudoThickness' in ds.keys()
            and 'SpecVol' in ds.keys()
        ):
            ds['layerThickness'] = geom_thickness_from_ds(ds, config=config)
        if (
            self.model == 'omega'
            and 'SpecVol' not in ds.keys()
            and 'Temperature' in ds.keys()
            and 'Salinity' in ds.keys()
            and 'SurfacePressure' in ds.keys()
        ):
            ds_mpas = self.map_from_native_model_vars(ds)
            iter_count = get_iter_count_for_eos(config)
            _, _, spec_vol = pressure_and_spec_vol_from_state_at_geom_height(
                config,
                ds_mpas.layerThickness,
                ds_mpas.temperature,
                ds_mpas.salinity,
                ds_mpas.SurfacePressure,
                iter_count=iter_count,
            )
            ds['SpecVol'] = spec_vol
        if (
            self.model == 'omega'
            and 'vertVelocityTop' not in ds.keys()
            and 'PseudoThickness' in ds.keys()
            and 'SpecVol' in ds.keys()
            and 'VerticalPseudoVelocity' in ds.keys()
            # the vertical coordinate file, not the mesh, is what this
            # derivation reads
            and vert_filename is not None
        ):
            ds_vert = self.open_model_dataset(vert_filename, config)
            geom_z_inter, geom_z_mid = geom_height_from_pseudo_height(
                geom_z_bot=ds_vert.bottomDepth,
                h_tilde=ds.PseudoThickness.rename(
                    {'NVertLayers': 'nVertLevels', 'NCells': 'nCells'}
                ),
                spec_vol=ds.SpecVol.rename(
                    {'NVertLayers': 'nVertLevels', 'NCells': 'nCells'}
                ),
                min_level_cell=ds_vert.minLevelCell,
                max_level_cell=ds_vert.maxLevelCell,
            )
            n_time = geom_z_inter.sizes['time']
            n_vert_levels_p1 = geom_z_inter.sizes['nVertLevelsP1']
            n_cells = geom_z_inter.sizes['nCells']
            spec_vol_inter_vals = np.zeros((n_time, n_vert_levels_p1, n_cells))
            for i_time in range(ds.sizes['time']):
                for i_cell in range(n_cells):
                    x_vals = geom_z_inter.isel(nCells=i_cell, time=i_time)
                    xp_vals = geom_z_mid.isel(nCells=i_cell, time=i_time)
                    fp_vals = ds.SpecVol.isel(NCells=i_cell, time=i_time)
                    interp_vals = np.interp(
                        x_vals.values,
                        xp_vals.values,
                        fp_vals.values,
                    )
                    spec_vol_inter_vals[i_time, :, i_cell] = interp_vals
            spec_vol_inter = xr.DataArray(
                spec_vol_inter_vals,
                dims=['time', 'NVertLayersP1', 'NCells'],
            )
            ds['vertVelocityTop'] = (
                ds.VerticalPseudoVelocity * spec_vol_inter * RhoSw
            )
        ds = self.map_from_native_model_vars(ds)
        # the conversion is the last thing that happens to the tracers: the
        # derivations above feed the model's own tracers into TEOS-10 and
        # would be wrong if they were converted first
        ds = self._convert_tracers_from_model(
            ds,
            config,
            tracer_convention=tracer_convention,
            mesh_filename=mesh_filename,
            lon=lon,
            lat=lat,
            logger=logger,
        )
        if reconstruct_variables is not None:
            if mesh_filename is None:
                raise ValueError(
                    'mesh_filename must be provided to open_model_dataset '
                    'for variable reconstruction'
                )
            if reconstruct_method == 'RBF' and coeffs_filename is None:
                raise ValueError(
                    'coeffs_filename must be provided to open_model_dataset '
                    'for variable reconstruction'
                )
            ds_mesh = self.open_model_dataset(mesh_filename, config)
            if (
                reconstruct_method == 'LSTSQ'
                and not _reconstruction_weights_in_dataset(ds_mesh)
            ):
                raise ValueError(
                    'Reconstruction weights are not present in the mesh '
                    'dataset; cannot reconstruct variables using LSTSQ method'
                )

            ds = _add_reconstructed_variables_to_dataset(
                ds,
                reconstruct_variables,
                ds_mesh,
                coeffs_filename,
                reconstruct_method,
            )
        return ds

    def _convert_tracers_for_model(
        self, ds, config, tracer_convention, lon, lat, logger
    ):
        """
        Convert ``temperature`` and ``salinity`` from the convention they are
        given in to the one the ocean model expects: conservative temperature
        and absolute salinity for Omega, potential temperature and practical
        salinity for MPAS-Ocean.

        The conventions only differ for the TEOS-10 equation of state, so this
        is a no-op for any other ``eos_type``, as it is when the tracers are
        already in the model's convention.
        """
        if not config.has_option('ocean', 'eos_type'):
            return ds
        if config.get('ocean', 'eos_type').strip() != 'teos-10':
            return ds

        if tracer_convention is None:
            # tasks build their initial condition in the convention implied by
            # the equation of state unless they say otherwise
            tracer_convention = 'teos-10'

        target = 'teos-10' if self.model == 'omega' else 'mpas-ocean'
        if tracer_convention == target:
            return ds

        pressure = pressure_for_tracer_conversion(ds, config, logger=logger)
        lon, lat = _lon_lat_for_tracer_conversion(ds, config, lon=lon, lat=lat)

        return convert_tracers(
            ds,
            source=tracer_convention,
            target=target,
            pressure=pressure,
            lon=lon,
            lat=lat,
        )

    def _convert_tracers_from_model(
        self, ds, config, tracer_convention, mesh_filename, lon, lat, logger
    ):
        """
        Convert ``temperature`` and ``salinity`` from the convention the ocean
        model uses to the ``tracer_convention`` the caller has asked for, so
        that analysis and visualization can work in one convention no matter
        which model ran.

        Unlike on write, there is nothing to infer: a caller that does not ask
        for a convention gets the tracers as the model wrote them.
        """
        if tracer_convention is None:
            return ds
        if not config.has_option('ocean', 'eos_type'):
            return ds
        if config.get('ocean', 'eos_type').strip() != 'teos-10':
            return ds

        if self.model is None:
            self.model = config.get('ocean', 'model')

        source = 'teos-10' if self.model == 'omega' else 'mpas-ocean'
        if tracer_convention == source:
            return ds

        pressure = pressure_for_tracer_conversion(ds, config, logger=logger)
        lon, lat = self._lon_lat_from_mesh(
            config, mesh_filename=mesh_filename, lon=lon, lat=lat
        )

        return convert_tracers(
            ds,
            source=source,
            target=tracer_convention,
            pressure=pressure,
            lon=lon,
            lat=lat,
        )

    def _lon_lat_from_mesh(self, config, mesh_filename, lon, lat):
        """
        Determine the longitude and latitude (in degrees) at which to convert
        the tracers in a dataset being read.

        Unlike an initial condition being written, a dataset being read has
        typically had its horizontal mesh variables removed (or never had
        them), so the locations come from the mesh file rather than from the
        dataset itself.
        """
        if (lon is None) != (lat is None):
            raise ValueError(
                'lon and lat must either both be given or both be omitted'
            )
        if lon is not None:
            return lon, lat

        if mesh_filename is None:
            raise ValueError(
                'Converting tracers to another convention requires the '
                'location of each cell.  Pass mesh_filename to '
                'open_model_dataset(), or an explicit lon and lat.'
            )

        ds_mesh = self.open_model_dataset(mesh_filename, config)
        return _lon_lat_for_tracer_conversion(ds_mesh, config, strict=True)

    def _check_vars_present(self, ds, native_vars, context):
        """
        Raise ValueError if any variable in native_vars is absent from ds.
        """
        missing = [v for v in native_vars if v not in ds]
        if missing:
            raise ValueError(
                f'{context} requires the following variables that are '
                'missing from the dataset: ' + ', '.join(missing)
            )

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

    def _read_variables_yaml(self):
        """
        Read horiz_mesh_vars and vert_coord_vars from variables.yaml
        """
        package = 'polaris.ocean.model'
        filename = 'variables.yaml'
        text = imp_res.files(package).joinpath(filename).read_text()
        yaml_data = YAML(typ='rt')
        nested_dict = yaml_data.load(text)
        self.horiz_mesh_vars = list(
            nested_dict['ocean']['horiz_mesh_variables']
        )
        self.vert_coord_vars = list(
            nested_dict['ocean']['vert_coord_variables']
        )
        self.state_vars = list(nested_dict['ocean']['state_variables'])
        model_section_map = {'mpas-ocean': 'mpas-ocean', 'omega': 'Omega'}
        model_key = model_section_map.get(self.model or '')
        if model_key:
            extra = nested_dict.get(model_key, {}).get(
                'horiz_mesh_variables', []
            )
            self.horiz_mesh_vars.extend(extra)
            extra = nested_dict.get(model_key, {}).get(
                'vert_coord_variables', []
            )
            self.vert_coord_vars.extend(extra)
            extra = nested_dict.get(model_key, {}).get('state_variables', [])
            self.state_vars.extend(extra)

    def _read_var_map(self):
        """
        Read the map from MPAS-Ocean to Omega dimension and variable names
        """
        if self.mpaso_to_omega_var_map is not None:
            return
        package = 'polaris.ocean.model'

        filename = 'mpaso_to_omega.yaml'
        text = imp_res.files(package).joinpath(filename).read_text()
        yaml_data = YAML(typ='rt')
        nested_dict = yaml_data.load(text)
        self.mpaso_to_omega_dim_map = nested_dict['dimensions']
        self.mpaso_to_omega_var_map = nested_dict['variables']

        self._read_variables_yaml()

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


def _lon_lat_for_tracer_conversion(
    ds, config, lon=None, lat=None, strict=False
):
    """
    Determine the longitude and latitude (in degrees) at which to convert
    tracers between the TEOS-10 and MPAS-Ocean conventions.

    Explicit ``lon`` and ``lat`` arguments win.  Otherwise, per-cell
    ``lonCell`` and ``latCell`` (converted from radians) are used on a
    spherical mesh and the nominal location from config options is used on a
    planar mesh.

    Parameters
    ----------
    ds : xarray.Dataset
        A dataset with the mesh information: the ``on_a_sphere`` attribute
        and, if the mesh is on a sphere, ``lonCell`` and ``latCell``

    config : polaris.config.PolarisConfigParser
        Configuration options, including ``nominal_lon`` and ``nominal_lat``
        in the ``ocean`` section

    lon : float or xarray.DataArray, optional
        An explicit longitude (or longitudes) in degrees

    lat : float or xarray.DataArray, optional
        An explicit latitude (or latitudes) in degrees

    strict : bool, optional
        Whether a missing ``on_a_sphere`` attribute is an error rather than
        an indication that the mesh is planar.  A mesh file without the
        attribute is invalid, but an initial condition being assembled by a
        step may not have picked it up.

    Returns
    -------
    lon : float or xarray.DataArray
        The longitude(s) in degrees

    lat : float or xarray.DataArray
        The latitude(s) in degrees
    """
    if (lon is None) != (lat is None):
        raise ValueError(
            'lon and lat must either both be given or both be omitted'
        )
    if lon is not None:
        return lon, lat

    on_a_sphere = ds.attrs.get('on_a_sphere')
    if on_a_sphere is None:
        if strict:
            raise ValueError(
                'A tracer conversion needs to know whether the mesh is on a '
                'sphere but the mesh dataset has no on_a_sphere attribute'
            )
        on_a_sphere = 'NO'

    on_a_sphere = str(on_a_sphere).strip().lower()
    if on_a_sphere == 'yes':
        # planar meshes carry meaningless lonCell/latCell, so they may only
        # be used when the mesh really is on a sphere
        missing = [name for name in ('lonCell', 'latCell') if name not in ds]
        if missing:
            raise ValueError(
                'A tracer conversion on a spherical mesh requires per-cell '
                'locations but the dataset is missing: ' + ', '.join(missing)
            )
        return np.rad2deg(ds.lonCell), np.rad2deg(ds.latCell)

    section = config['ocean']
    return section.getfloat('nominal_lon'), section.getfloat('nominal_lat')


def _add_reconstructed_variables_to_dataset(
    ds,
    reconstruct_variables,
    ds_mesh,
    coeffs_filename,
    reconstruct_method: Literal['RBF', 'LSTSQ'],
):
    """
    Add reconstructed vector variables to the dataset if requested.
    Parameters
    ----------
    ds : xarray.Dataset
        The dataset to add reconstructed variables to.

    reconstruct_variables : list of str or None
        List of variable names to reconstruct.

    ds_mesh : xarray.Dataset
        Mesh dataset on which to perform the reconstruction.

    coeffs_filename : str
        Path to the coefficients NetCDF file.

    reconstruct_method : {'RBF', 'LSTSQ'}
        Method to use for reconstructing vector variables.

    Returns
    -------
    ds : xarray.Dataset
        The dataset with reconstructed variables added.
    """
    if reconstruct_variables is None:
        return ds

    out_var_names = {}
    for variable in reconstruct_variables:
        out_var_name = (
            variable.replace('normal', '').lower()
            if 'normal' in variable
            else variable
        )
        if f'{out_var_name}Zonal' in ds and f'{out_var_name}Meridional' in ds:
            # already reconstructed, e.g. by MPAS-Ocean itself
            continue
        out_var_names[variable] = out_var_name

    if len(out_var_names) == 0:
        return ds

    for variable in out_var_names:
        if variable not in ds:
            raise ValueError(
                f"User requested vector reconstruction for '{variable}' "
                "but it isn't present in the dataset."
            )

    if reconstruct_method == 'RBF':
        ds_coeff = open_dataset(coeffs_filename)
        coeffs_reconstruct = ds_coeff.coeffs_reconstruct

        if ds_coeff.sizes['nCells'] != ds_mesh.sizes['nCells']:
            print(
                f'The sizes of coefficient dataset do not match mesh dataset;'
                f' exiting without reconstructing {reconstruct_variables}'
            )
            return ds

    for variable, out_var_name in out_var_names.items():
        if reconstruct_method == 'RBF':
            reconstruct_variable(
                out_var_name,
                ds[variable],
                ds_mesh,
                coeffs_reconstruct,
                ds,
                quiet=True,
            )

        elif reconstruct_method == 'LSTSQ':
            stencil = ds_mesh.reconstructStencilCell
            weights = ds_mesh.reconstructWeightsCell

            u_x, u_y, u_z = tangential_reconstruction(
                ds_mesh, ds[variable], stencil=stencil, weights=weights
            )
            if ds_mesh.attrs['on_a_sphere'] == 'NO':
                ds[f'{out_var_name}X'] = u_x
                ds[f'{out_var_name}Y'] = u_y
            else:
                u_zonal, u_merid, _ = cartesian_to_local_geographic(
                    ds_mesh, u_x, u_y, u_z
                )

                ds[f'{out_var_name}Zonal'] = u_zonal
                ds[f'{out_var_name}Meridional'] = u_merid

        if not (
            f'{out_var_name}Zonal' in ds and f'{out_var_name}Meridional' in ds
        ):
            print(f'Failed to reconstruct {out_var_name}')

        return ds


def _reconstruction_weights_in_dataset(ds, vertices=False):
    """
    Check if the reconstruction weights are present in the dataset.

    Parameters
    ----------
    ds : xarray.Dataset
        The dataset to check for reconstruction weights.
    vertices: bool, optional (default False)
        Whether to check for vertex centered reconstruction weights

    Returns
    -------
    present
        True if reconstruction weights are present, False otherwise.
    """
    present = any(var.lower() == 'reconstructstencilcell' for var in ds)
    present &= any(var.lower() == 'reconstructweightscell' for var in ds)

    if vertices:
        present &= any(var.lower() == 'reconstructstencilvertex' for var in ds)
        present &= any(var.lower() == 'reconstructweightsvertex' for var in ds)

    return present


# create a single module-level instance available to other components
ocean = Ocean()
