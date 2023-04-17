from polaris.remap import MappingFileStep


class VizMap(MappingFileStep):
    """
    A step for making a mapping file for cosine bell viz

    Attributes
    ----------
    mesh_name : str
        The name of the mesh
    """
    def __init__(self, test_case, name, subdir, mesh_name):
        """
        Create the step

        Parameters
        ----------
        test_case : polaris.TestCase
            The test case this step belongs to

        name : str
            The name of the step

        subdir : str
            The subdirectory in the test case's work directory for the step

        mesh_name : str
            The name of the mesh
        """
        super().__init__(test_case=test_case, name=name, subdir=subdir,
                         ntasks=128, min_tasks=1)
        self.mesh_name = mesh_name
        self.add_input_file(filename='mesh.nc', target='../mesh/mesh.nc')

    def run(self):
        """
        Set up the source and destination grids for this step
        """
        config = self.config
        section = config['cosine_bell_viz']
        dlon = section.getfloat('dlon')
        dlat = section.getfloat('dlat')
        method = section.get('remap_method')
        self.src_from_mpas(filename='mesh.nc', mesh_name=self.mesh_name)
        self.dst_global_lon_lat(dlon=dlon, dlat=dlat)
        self.method = method

        super().run()
