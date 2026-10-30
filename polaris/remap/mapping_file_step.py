import os

from pyremap import Remapper

from polaris import Step
from polaris.remap.scrip_descriptor import ScripFileDescriptor


class MappingFileStep(Step):
    """
    A step for creating a mapping file between grids

    Attributes
    ----------
    remapper : pyremap.Remapper
        An object for creating a mapping file and remapping data between
        grids
    """

    def __init__(
        self,
        component,
        name,
        subdir=None,
        indir=None,
        ntasks=None,
        min_tasks=None,
        map_filename=None,
        method='bilinear',
    ):
        """
        Create a new step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        name : str
            the name of the step

        subdir : str, optional
            the subdirectory for the step.  If neither this nor ``indir``
             are provided, the directory is the ``name``

        indir : str, optional
            the directory the step is in, to which ``name`` will be appended

        ntasks : int, optional
            the target number of MPI tasks the step would ideally use

        min_tasks : int, optional
            the number of MPI tasks the step requires

        map_filename : str, optional
            The name of the output mapping file,
            ``map_{source_type}_{dest_type}_{method}.nc`` by default

        method : {'bilinear', 'neareststod', 'conserve'}, optional
            The method of interpolation used
        """
        super().__init__(
            component=component,
            name=name,
            subdir=subdir,
            indir=indir,
            ntasks=ntasks,
            min_tasks=min_tasks,
        )
        # use_tmp=False because pyremap would otherwise put the SCRIP and
        # MOAB .h5m files in a temporary directory under /tmp, which is
        # node-local on many HPC machines.  The MPI tasks running the mapping
        # tool are typically spread over several nodes, so the files must be
        # in the step's work directory on a shared filesystem.
        self.remapper = Remapper(
            ntasks=ntasks,
            map_filename=map_filename,
            method=method,
            use_tmp=False,
        )
        # the mapping tool's command can only be made once the grids have
        # been read and the step's tasks decided, in runtime_setup(), but the
        # step has to say from the start that it launches one
        self.args = []

    def src_from_scrip(self, filename, mesh_name, regional=True):
        """
        Read the source grid from a SCRIP file

        Parameters
        ----------
        filename : str
            The path of the SCRIP file, relative to the step's work directory

        mesh_name : str
            The name of the mesh, used to give mapping files unique names

        regional : bool, optional
            Whether the mesh is regional rather than global
        """
        self.remapper.src_descriptor = ScripFileDescriptor(
            filename=filename, mesh_name=mesh_name, regional=regional
        )

    def dst_from_scrip(self, filename, mesh_name, regional=True):
        """
        Read the destination grid from a SCRIP file

        Parameters
        ----------
        filename : str
            The path of the SCRIP file, relative to the step's work directory

        mesh_name : str
            The name of the mesh, used to give mapping files unique names

        regional : bool, optional
            Whether the mesh is regional rather than global
        """
        self.remapper.dst_descriptor = ScripFileDescriptor(
            filename=filename, mesh_name=mesh_name, regional=regional
        )

    def runtime_setup(self):
        """
        Write the files the mapping tool reads and set the command that
        creates the mapping file
        """
        config = self.config
        remapper = self.remapper
        remapper.map_tool = config.get('mapping', 'map_tool')
        remapper.ntasks = self.ntasks

        src = remapper.src_grid_info
        dst = remapper.dst_grid_info

        if 'type' not in src and remapper.src_descriptor is None:
            raise ValueError('None of the "src_from_*()" methods were called')

        if 'type' not in dst and remapper.dst_descriptor is None:
            raise ValueError('None of the "dst_from_*()" methods were called')

        # to absolute paths for when the remapper is used in another step
        for info in [src, dst]:
            if 'filename' in info:
                info['filename'] = os.path.abspath(
                    os.path.join(self.work_dir, info['filename'])
                )
        for descriptor in [remapper.src_descriptor, remapper.dst_descriptor]:
            if isinstance(descriptor, ScripFileDescriptor):
                descriptor.filename = os.path.abspath(
                    os.path.join(self.work_dir, descriptor.filename)
                )

        self.args = [remapper.prepare_map(logger=self.logger)]
        remapper.map_filename = os.path.abspath(remapper.map_filename)
