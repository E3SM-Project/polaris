from polaris.ocean.tasks.isomip_plus.projection import get_projection_string
from polaris.remap import MappingFileStep


class TopoMap(MappingFileStep):
    """
    A step for making a mapping file from a source topography file to the
    ISOMIP+ mesh

    Attributes
    ----------
    mesh_name : str
        The name of the mesh
    """
    def __init__(self, component, name, subdir, mesh_name, mesh_step,
                 mesh_filename):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        name : str
            The name of the step

        subdir : str
            The subdirectory for the step

        mesh_name : str
            The name of the mesh

        mesh_step : polaris.Step
            The base mesh step
        """
        super().__init__(component=component, name=name, subdir=subdir,
                         ntasks=128, min_tasks=1)
        self.mesh_name = mesh_name

        # since all geometry is on the same mesh, we'll use Ocean1 here
        geom_filename = 'Ocean1_input_geom_v1.01.nc'
        self.add_input_file(filename='input_topo.nc',
                            target=geom_filename,
                            database='isomip_plus')
        self.add_input_file(
            filename='mesh.nc',
            work_dir_target=f'{mesh_step.path}/{mesh_filename}')

    def runtime_setup(self):
        """
        Set up the source and destination grids for this step
        """
        config = self.config
        section = config['isomip_plus']
        lat0 = section.getfloat('lat0')
        method = section.get('topo_remap_method')
        proj_str = get_projection_string(lat0)
        self.src_from_proj(filename='input_topo.nc',
                           mesh_name='ISOMIP+_input_topo',
                           x_var='x',
                           y_var='y',
                           proj_str=proj_str)
        self.dst_from_mpas(filename='mesh.nc', mesh_name=self.mesh_name)
        self.method = method

        super().runtime_setup()
