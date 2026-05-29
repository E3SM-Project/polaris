from polaris.ocean.model import OceanModelStep


class Forward(OceanModelStep):
    """
    A step for performing forward ocean component runs as part of the cosine
    bell test case
    """

    def __init__(
        self,
        component,
        package,
        name='forward',
        indir=None,
        subdir=None,
        update_eos=False,
        yaml_filename='forward.yaml',
        mesh_filename='mesh.nc',
        init_filename='init.nc',
        graph_filename='culled_graph.info',
        output_filename='output.nc',
        ntasks=None,
        min_tasks=None,
        options=None,
        replacements=None,
        validate_vars=None,
        check_properties=None,
        resolution_for_cell_count=None,
    ):
        """
        Create a new step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        name : str
            The name of the step

        subdir : str
            The subdirectory for the step

        """
        super().__init__(
            component=component,
            name=name,
            indir=indir,
            subdir=subdir,
            ntasks=ntasks,
            min_tasks=min_tasks,
            update_eos=update_eos,
            openmp_threads=1,
            graph_target=graph_filename,
        )
        self.mesh_filename = mesh_filename
        self.init_filename = init_filename
        self.graph_filename = graph_filename
        self.resolution = resolution_for_cell_count
        # make sure output is double precision
        self.add_yaml_file('polaris.ocean.config', 'output.yaml')

        # this is set in the yaml file
        # self.add_yaml_file('polaris.ocean.eos', 'teos10.yaml')

        self.add_yaml_file(
            package,
            yaml_filename,
            template_replacements=replacements,
        )

        if options is not None:
            for config_model in options:
                self.add_model_config_options(
                    options=options[config_model], config_model=config_model
                )

        # TODO replace validate_vars with all model-specific state vars
        self.add_output_file(
            filename=output_filename,
            validate_vars=validate_vars,
            check_properties=check_properties,
        )

    def setup(self):
        """
        TEMP: symlink initial condition to name hard-coded in Omega
        """
        super().setup()
        config = self.config
        model = config.get('ocean', 'model')
        # TODO: remove as soon as Omega no longer hard-codes this file
        if model == 'omega':
            self.add_input_file(
                target=self.mesh_filename,
                filename='OmegaMesh.nc',
                database='realistic_global',
            )
            self.add_input_file(
                target=self.init_filename,
                filename='init.nc',
                database='realistic_global',
            )
            # TODO we need to add this file to input database if we want to
            # reconstruct zonal, meridional components before Omega has those
            # capabilities natively
            # self.add_input_file(
            #    target='coeffs.nc',
            #    filename='coeffs.nc',
            #    database='realistic_global',
            # )
        else:
            self.add_input_file(
                target='culled_graph.info',
                filename=self.graph_filename,
                database='realistic_global',
            )

    def compute_cell_count(self):
        """
        Compute the approximate number of cells in the mesh, used to constrain
        resources

        Returns
        -------
        cell_count : int or None
            The approximate number of cells in the mesh
        """
        # Consider getting ds_mesh.sizes['nCells'] from file in input database
        if self.resolution is None:
            raise ValueError(
                'Resolution for cell count is required for realistic_global '
                'tests'
            )
        cell_count = 4e8 / self.resolution**2
        return cell_count
