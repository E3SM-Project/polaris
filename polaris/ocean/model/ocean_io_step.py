from typing import TYPE_CHECKING

import xarray as xr

from polaris import Step
from polaris.ocean.model.ocean_model_files_mixin import OceanModelFilesMixin

if TYPE_CHECKING:
    # Keep Ocean as a type-only import. Importing it at runtime pulls
    # polaris.tasks.ocean back into polaris.ocean.model while that package is
    # still importing these step classes, creating a circular import.
    from polaris.tasks.ocean import Ocean


class OceanIOStep(Step, OceanModelFilesMixin):
    """
    A step that writes input and/or output files for Omega or MPAS-Ocean
    """

    # make sure component is of type Ocean, using a string to avoid circular
    # imports
    component: 'Ocean'

    def __init__(self, component: 'Ocean', **kwargs):
        super().__init__(component=component, **kwargs)

    def process_inputs_and_outputs(self) -> None:
        """
        Resolve ``<<<placeholder>>>`` filenames to configured names and drop
        ``<<<vert_coord>>>`` entries for MPAS-Ocean before delegating to
        the base :py:class:`~polaris.Step` processing.
        """
        self._resolve_model_file_placeholders()
        super().process_inputs_and_outputs()

    def add_output_files_for_ocean_model_input(
        self,
        horiz_mesh_filename=None,
        vert_coord_filename=None,
        init_filename=None,
        base_mesh_filename=None,
        graph_filename=None,
    ):
        """
        Register output files that will be consumed by the ocean model as
        inputs (horizontal mesh, initial condition, and model-specific files).

        Parameters
        ----------
        horiz_mesh_filename : str, optional
            Local filename for the horizontal mesh output; defaults to the
            ``horiz_mesh_filename`` option in ``[ocean_staged_files]``.

        vert_coord_filename : str, optional
            Local filename for the vertical-coordinate output (Omega only);
            defaults to the ``vert_coord_filename`` option in
            ``[ocean_staged_files]``.

        init_filename : str, optional
            Local filename for the initial-state output; defaults to the
            ``init_filename`` option in ``[ocean_staged_files]``.

        base_mesh_filename : str, optional
            If provided, also register this filename as an output (used when
            the step writes both a base and a culled mesh, e.g.
            ``'base_mesh.nc'``).

        graph_filename : str, optional
            If provided, register this filename as an output for MPAS-Ocean
            only (e.g. ``'culled_graph.info'``).  Ignored for Omega.
        """
        config = self.config
        model = config.get('ocean', 'model')

        if horiz_mesh_filename is None:
            horiz_mesh_filename = self.get_horiz_mesh_filename()
        if vert_coord_filename is None:
            vert_coord_filename = self.get_vert_coord_filename()
        if init_filename is None:
            init_filename = self.get_init_filename()

        if base_mesh_filename is not None:
            self.add_output_file(filename=base_mesh_filename)
        self.add_output_file(filename=horiz_mesh_filename)
        self.add_output_file(filename=init_filename)
        if model == 'omega':
            self.add_output_file(filename=vert_coord_filename)
        if model == 'mpas-ocean' and graph_filename is not None:
            self.add_output_file(filename=graph_filename)

    def open_vert_coord_dataset(
        self, ds_init, vert_coord_filename=None, **kwargs
    ):
        """
        Return the dataset containing vertical-coordinate variables
        (``bottomDepth``, ``minLevelCell``, ``maxLevelCell``,
        ``vertCoordMovementWeights`` and either ``restingThickness`` or
        ``RefPseudoThickness``).

        For Omega: opens *vert_coord_filename* (defaults to
        :py:meth:`get_vert_coord_filename`) via
        :py:meth:`open_model_dataset` so Omega variable names are mapped to
        their MPAS-Ocean equivalents.

        For MPAS-Ocean: returns the set of vertical-coordinate variables from
        *ds_init* (those variables live in the initial state file).

        Parameters
        ----------
        ds_init : xarray.Dataset
            The already-opened initial-condition dataset.
        vert_coord_filename : str, optional
            Local filename of the vertical-coordinate file.  Defaults to
            :py:meth:`get_vert_coord_filename`.  Pass an explicit name when
            using per-resolution files (e.g. ``'vert_coord_r04.nc'``).
        **kwargs
            Forwarded to :py:meth:`open_model_dataset`.
        """
        model = self.config.get('ocean', 'model')
        if model == 'omega':
            if vert_coord_filename is None:
                vert_coord_filename = self.get_vert_coord_filename()
            ds_vert_coord = self.open_model_dataset(
                vert_coord_filename, config=self.config, **kwargs
            )
        elif model == 'mpas-ocean':
            ds_vert_coord = xr.Dataset()
            if self.component.vert_coord_vars is None:
                raise ValueError(
                    'Vertical coordinate variables not defined in the Ocean '
                    'component'
                )
            for var in self.component.vert_coord_vars:
                if var not in ds_init:
                    raise ValueError(
                        f"Expected vertical coordinate variable '{var}' not "
                        'found in initial condition dataset'
                    )
                ds_vert_coord[var] = ds_init[var]
        else:
            raise ValueError(f'Unsupported ocean model: {model}')

        return ds_vert_coord

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

    def write_horiz_mesh_dataset(self, ds, filename, config):
        """
        Write a horizontal mesh dataset, validating that all expected mesh
        variables are present before writing.

        Parameters
        ----------
        ds : xarray.Dataset
            A dataset containing MPAS-Ocean variable names including all
            horizontal mesh variables

        filename : str
            The path for the NetCDF file to write

        config : polaris.config.PolarisConfigParser
            Configuration for the task; forwarded to the Ocean component.
        """
        self.component.write_horiz_mesh_dataset(ds, filename, config)

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

    def add_output_file(
        self,
        filename,
        validate_vars=None,
        check_properties=None,
        validate_class=None,
    ):
        """
        Add an output file, optionally resolving ``validate_class`` to a
        pre-defined list of variables from the Ocean component.

        Parameters
        ----------
        filename : str
            The output filename to register.

        validate_vars : list of str, optional
            Explicit list of variable names to validate against a baseline.
            Mutually exclusive with ``validate_class``.

        validate_class : str, optional
            A named class of variables to validate.  Currently only
            ``'state'`` is supported, which resolves to
            ``self.component.state_vars`` mapped to the native model's
            variable names.

        **kwargs
            Forwarded to :py:meth:`polaris.Step.add_output_file`.
        """
        if validate_class is not None:
            if validate_class == 'state':
                if self.component.state_vars is None:
                    self.component._read_variables_yaml()
                assert self.component.state_vars is not None
                validate_vars = list(
                    dict.fromkeys(
                        self.component.map_var_list_to_native_model(
                            self.component.state_vars
                        )
                        + (validate_vars if validate_vars is not None else [])
                    )
                )
            else:
                raise ValueError(
                    f"Unknown validate_class '{validate_class}'. "
                    "Currently only 'state' is supported."
                )
        super().add_output_file(
            filename=filename,
            validate_vars=validate_vars,
            check_properties=check_properties,
        )
