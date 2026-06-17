from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from polaris.config import PolarisConfigParser
    from polaris.tasks.ocean import Ocean

# Maps placeholder filenames to their [ocean_staged_files] config option names.
_PLACEHOLDER_MAP = {
    '<<<horiz_mesh>>>': 'horiz_mesh_filename',
    '<<<vert_coord>>>': 'vert_coord_filename',
    '<<<init>>>': 'init_filename',
}


class OceanModelFilesMixin:
    """
    Mixin providing access to the ``[ocean_staged_files]`` config section and
    the shared placeholder mechanism for the three canonical ocean dataset
    files (horizontal mesh, vertical coordinate, initial state).

    Must be combined with a Step subclass that sets ``self.config`` and
    provides ``self.add_input_file()``.  The ``add_*_input_file()`` methods
    are safe to call from ``__init__()`` because the model check is deferred
    to :py:meth:`_resolve_model_file_placeholders`, which is called at
    ``process_inputs_and_outputs()`` time.
    """

    component: 'Ocean'
    # These attributes and methods are provided by the Step base class:
    config: 'PolarisConfigParser'
    input_data: list[dict[str, Any]]
    add_input_file: Callable[..., None]

    # --- filename getters ---

    def get_horiz_mesh_filename(self) -> str:
        """
        Get the configured local filename for the horizontal mesh file.
        """
        return self._get_model_input_filename('horiz_mesh_filename')

    def get_vert_coord_filename(self) -> str:
        """
        Get the configured local filename for the vertical coordinate file.
        """
        return self._get_model_input_filename('vert_coord_filename')

    def get_init_filename(self) -> str:
        """
        Get the configured local filename for the initial-condition file.
        """
        return self._get_model_input_filename('init_filename')

    # --- input file registration ---

    def add_horiz_mesh_input_file(self, **kwargs) -> None:
        """
        Add the horizontal-mesh input file using a placeholder that is
        resolved to the configured filename at
        :py:meth:`process_inputs_and_outputs` time.  Safe to call from
        ``__init__()``.

        Parameters
        ----------
        **kwargs
            Additional keyword arguments forwarded to
            :py:meth:`polaris.Step.add_input_file`.
        """
        self.add_input_file(filename='<<<horiz_mesh>>>', **kwargs)

    def add_vert_coord_input_file(self, filename=None, **kwargs) -> None:
        """
        Add the vertical-coordinate input file.

        When *filename* is ``None`` (the default), the
        ``'<<<vert_coord>>>'`` placeholder is used.  The placeholder is
        resolved at :py:meth:`process_inputs_and_outputs` time and silently
        dropped for MPAS-Ocean (no separate vert_coord file exists).  Safe
        to call from ``__init__()``.

        When *filename* is provided explicitly (e.g. ``'vert_coord_r04.nc'``
        for multi-resolution steps), the entry is added directly for Omega
        only and must be called from ``setup()`` or later (requires
        ``self.config``).

        Parameters
        ----------
        filename : str, optional
            Explicit local filename, overriding the placeholder.
        **kwargs
            Additional keyword arguments forwarded to
            :py:meth:`polaris.Step.add_input_file`.
        """
        if filename is None:
            self.add_input_file(filename='<<<vert_coord>>>', **kwargs)
        else:
            model = self.config.get('ocean', 'model')
            if model == 'omega':
                self.add_input_file(filename=filename, **kwargs)

    def add_init_input_file(self, **kwargs) -> None:
        """
        Add the initial-condition input file using a placeholder that is
        resolved to the configured filename at
        :py:meth:`process_inputs_and_outputs` time.  Safe to call from
        ``__init__()``.

        Parameters
        ----------
        **kwargs
            Additional keyword arguments forwarded to
            :py:meth:`polaris.Step.add_input_file`.
        """
        self.add_input_file(filename='<<<init>>>', **kwargs)

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

        check_properties : dict, optional
            Forwarded to :py:meth:`polaris.Step.add_output_file`.

        validate_class : str, optional
            A named class of variables to validate.  Currently only
            ``'state'`` is supported, which resolves to
            ``self.component.state_vars`` mapped to the native model's
            variable names.  The resulting list is unioned with any
            explicitly supplied ``validate_vars``.
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
        super().add_output_file(  # type: ignore[misc]
            filename=filename,
            validate_vars=validate_vars,
            check_properties=check_properties,
        )

    # --- shared placeholder resolution ---

    def _resolve_model_file_placeholders(self) -> None:
        """
        Scan ``self.input_data``, replace placeholder filenames with the
        configured names from ``[ocean_staged_files]``, and drop
        ``'<<<vert_coord>>>'`` entries for MPAS-Ocean.  Called at the top of
        :py:meth:`process_inputs_and_outputs` by both
        :py:class:`~polaris.ocean.model.OceanModelStep` and
        :py:class:`~polaris.ocean.model.OceanIOStep`.
        """
        model = self.config.get('ocean', 'model')
        keep = []
        for entry in self.input_data:
            fn = entry['filename']
            if fn == '<<<vert_coord>>>' and model != 'omega':
                continue
            if fn in _PLACEHOLDER_MAP:
                entry['filename'] = self._get_model_input_filename(
                    _PLACEHOLDER_MAP[fn]
                )
            keep.append(entry)
        self.input_data = keep

    # --- private helper ---

    def _get_model_input_filename(self, option: str) -> str:
        section = 'ocean_staged_files'
        if not self.config.has_section(section):
            raise ValueError(
                f'Config section [{section}] is required to determine model '
                f'input filenames, but it was not found.'
            )
        if not self.config.has_option(section, option):
            raise ValueError(
                f'Config option {option!r} is required to determine model '
                f'input filenames, but it was not found in [{section}].'
            )
        return self.config.get(section, option)
