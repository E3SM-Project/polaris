from polaris.model_step import ModelStep


class OceanModelStep(ModelStep):
    """
    An Omega or MPAS-Ocean step
    """

    def setup(self):
        """
        Set namelist options base on config options
        """
        config = self.config
        model = config.get('ocean', 'model')
        if model == 'omega':
            self.make_yaml = True
            self.make_namelist = False
            self.make_streams = False
        elif model == 'mpas-ocean':
            self.make_yaml = False
            self.make_namelist = True
            self.make_streams = True
        else:
            raise ValueError(f'Unexpected ocean model: {model}')

        super().setup()

    def map_yaml_to_namelist(self, options):
        """
        A mapping from yaml model config options to namelist options.  This
        method should be overridden for situations in which yaml config
        options have diverged in name or structure from their namelist
        counterparts (e.g. when translating from Omega yaml to MPAS-Ocean
        namelists)

        Parameters
        ----------
        options : dict
            A nested dictionary of yaml sections, options and value to use as
            replacements for existing values

        Returns
        -------
        options : dict
            A nested dictionary of namelist sections, options and value to use
            as replacements for existing values
        """
        # for now, just call the super class version but this will also handle
        # renaming in the future
        return super().map_yaml_to_namelist(options)

    def add_namelist_file(self, package, namelist):
        """
        Add a file with updates to namelist options to the step to be parsed
        when generating a complete namelist file if and when the step gets set
        up.

        Parameters
        ----------
        package : Package
            The package name or module object that contains ``namelist``

        namelist : str
            The name of the namelist replacements file to read from
        """
        raise ValueError('Input namelist files are not supported in '
                         'OceanModelStep')

    def add_streams_file(self, package, streams, template_replacements=None):
        """
        Add a streams file to the step to be parsed when generating a complete
        streams file if and when the step gets set up.

        Parameters
        ----------
        package : Package
            The package name or module object that contains the streams file

        streams : str
            The name of the streams file to read from

        template_replacements : dict, optional
            A dictionary of replacements, in which case ``streams`` must be a
            Jinja2 template to be rendered with these replacements
        """
        raise ValueError('Input streams files are not supported in '
                         'OceanModelStep')

    def update_model_config_at_runtime(self, options):
        """
        Update an existing namelist or yaml file with additional options.  This
        would typically be used for model config options that are only known at
        runtime, not during setup, typically those related to the number of
        nodes and cores.

        Parameters
        ----------
        options : dict
            A dictionary of options and value to replace namelist options with
            new values
        """

        config = self.config

        model = config.get('ocean', 'model')
        if model == 'omega':
            self.update_yaml_at_runtime(options)
        elif model == 'mpas-ocean':
            self.update_namelist_at_runtime(
                self.map_yaml_to_namelist(options))
        else:
            raise ValueError(f'Unexpected ocean model: {model}')
