import os

from pyremap import Remapper

from polaris import Step


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
        self.remapper = Remapper(
            ntasks=ntasks, map_filename=map_filename, method=method
        )

    def run(self):
        """
        Create the mappping file
        """
        config = self.config
        remapper = self.remapper
        remapper.map_tool = config.get('mapping', 'map_tool')
        remapper.ntasks = self.ntasks
        remapper.parallel_exec = config.get('parallel', 'parallel_executable')

        src = remapper.src_grid_info
        dst = remapper.dst_grid_info

        if 'type' not in src:
            raise ValueError('None of the "src_from_*()" methods were called')

        if 'type' not in dst:
            raise ValueError('None of the "dst_from_*()" methods were called')

        # to absolute paths for when the remapper is used in another step
        for info in [src, dst]:
            if 'filename' in info:
                info['filename'] = os.path.abspath(
                    os.path.join(self.work_dir, info['filename'])
                )

        remapper.build_map(logger=self.logger)
        remapper.map_filename = os.path.abspath(remapper.map_filename)
