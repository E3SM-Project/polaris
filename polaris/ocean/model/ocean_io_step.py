from polaris import Step
from polaris.ocean.model import io


class OceanIOStep(Step):
    """
    A step that writes input and/or output files for Omega or MPAS-Ocean
    """

    def __init__(self, component, **kwargs):
        super().__init__(component=component, **kwargs)

    def _effective_model(self) -> str:
        """
        Return the ocean model for this step.

        If the step (or a subclass) has set ``self.model`` explicitly (e.g.
        :py:class:`.InitialStateStep`), that value is used.  Otherwise the
        model is read from ``config['ocean']['model']``, which is the
        globally-configured model set during :py:meth:`.Ocean.configure`.
        """
        return getattr(self, 'model', None) or self.config.get(
            'ocean', 'model'
        )

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
            ``horiz_mesh_filename`` option in ``[ocean_model_files]``.

        vert_coord_filename : str, optional
            Local filename for the vertical-coordinate output (Omega only);
            defaults to the ``vert_coord_filename`` option in
            ``[ocean_model_files]``.

        init_filename : str, optional
            Local filename for the initial-state output; defaults to the
            ``init_filename`` option in ``[ocean_model_files]``.

        base_mesh_filename : str, optional
            If provided, also register this filename as an output (used when
            the step writes both a base and a culled mesh, e.g.
            ``'base_mesh.nc'``).

        graph_filename : str, optional
            If provided, register this filename as an output for MPAS-Ocean
            only (e.g. ``'culled_graph.info'``).  Ignored for Omega.
        """
        config = self.config
        model = self._effective_model()

        if horiz_mesh_filename is None:
            horiz_mesh_filename = config.get(
                'ocean_model_files', 'horiz_mesh_filename'
            )
        if vert_coord_filename is None:
            vert_coord_filename = config.get(
                'ocean_model_files', 'vert_coord_filename'
            )
        if init_filename is None:
            init_filename = config.get('ocean_model_files', 'init_filename')

        if base_mesh_filename is not None:
            self.add_output_file(filename=base_mesh_filename)
        self.add_output_file(filename=horiz_mesh_filename)
        self.add_output_file(filename=init_filename)
        if model == 'omega':
            self.add_output_file(filename=vert_coord_filename)
        if model == 'mpas-ocean' and graph_filename is not None:
            self.add_output_file(filename=graph_filename)

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
        return io.map_to_native_model_vars(ds, model=self._effective_model())

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
            Configuration for the task; forwarded to the I/O module.
        """
        io.write_model_dataset(
            ds, filename, config, model=self._effective_model()
        )

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
            Configuration for the task; forwarded to the I/O module.
        """
        io.write_horiz_mesh_dataset(
            ds, filename, config, model=self._effective_model()
        )

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
            Configuration for the task; forwarded to the I/O module.
        """
        io.write_vert_coord_dataset(
            ds, filename, config, model=self._effective_model()
        )

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
            Configuration for the task; forwarded to the I/O module.
        """
        io.write_initial_state_dataset(
            ds, filename, config, model=self._effective_model()
        )

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
        return io.map_from_native_model_vars(ds, model=self._effective_model())

    def open_model_dataset(self, filename, config, **kwargs):
        """
        Open the given dataset, mapping variable and dimension names from Omega
        to MPAS-Ocean names if appropriate

        Parameters
        ----------
        filename : str
            The path for the NetCDF file to open

        config : polaris.config.PolarisConfigParser
            Configuration for the task; forwarded to the I/O module.

        kwargs
            keyword arguments passed to `xarray.open_dataset()`

        Returns
        -------
        ds : xarray.Dataset
            The dataset with variables named as expected in MPAS-Ocean
        """
        return io.open_model_dataset(
            filename, config, model=self._effective_model(), **kwargs
        )
