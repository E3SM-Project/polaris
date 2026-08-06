import os

import xarray as xr
from mpas_tools.logging import check_call

from polaris.remap import MappingFileStep
from polaris.tasks.e3sm.init.component_inputs.models import check_seaice_model
from polaris.tasks.e3sm.init.component_inputs.names import get_mesh_short_name
from polaris.tasks.e3sm.init.component_inputs.partitions import get_core_list

#: The base name the partition files carry.  As with the ocean partitions,
#: the creation date is added when the files are staged, not here.
GRAPH_BASENAME = 'mpas-seaice.graph.info'

#: The QU60km sea-ice climatology the partitioning weights cells by, and the
#: mask of where ice is present in it.
PARTITION_DATABASE_FILES = (
    'seaice_QU60km_polar.nc',
    'icePresent_QU60km_polar.nc',
)


class SeaiceGraphPartitionStep(MappingFileStep):
    """
    A step for partitioning the sea-ice mesh.

    Sea-ice partitions are not ocean partitions with a different name.  They
    are weighted by where sea ice actually occurs, so that the cost of the ice
    physics is spread evenly rather than the cell count -- which is why this
    needs a QU60km climatology and a mapping file, and the ocean partitioning
    needs neither.

    The mesh being partitioned is
    :py:class:`~polaris.tasks.e3sm.init.component_inputs.seaice_mesh.SeaiceMeshStep`'s
    output.  Compass partitioned an ocean restart instead, which is the
    coupling D7 removes; it also had to drop ``cullCell`` from that file
    first, and the culled mesh this reads never had one.

    As with the ocean partitions, the core counts follow from a cell count
    that is not known until the mesh exists, so the partition files cannot be
    declared as outputs at setup.
    """

    def __init__(
        self,
        component,
        subdir,
        seaice_mesh_step,
        name='seaice_graph_partition',
    ):
        """
        Create a new step.

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to.

        subdir : str
            The subdirectory for the step.

        seaice_mesh_step : polaris.Step
            The step that wrote ``seaice_mesh.nc``.

        name : str, optional
            The name of the step.
        """
        super().__init__(
            component=component,
            name=name,
            subdir=subdir,
            # pyremap partitions the SCRIP files with "mbpart <ntasks>", which
            # rejects a request for a single partition, so the floor is 2
            ntasks=36,
            min_tasks=2,
            method='bilinear',
        )
        self.seaice_mesh_step = seaice_mesh_step
        self.mesh_short_name = None

        for filename in PARTITION_DATABASE_FILES:
            self.add_input_file(
                filename=filename,
                target=filename,
                database='partition',
                database_component='seaice',
            )
        self.add_input_file(
            filename='seaice_mesh.nc',
            work_dir_target=os.path.join(
                seaice_mesh_step.path, 'seaice_mesh.nc'
            ),
        )

    def setup(self):
        """
        Resolve what the mapping file is named after, before anything runs.
        """
        super().setup()
        check_seaice_model(self.config)
        self.mesh_short_name = get_mesh_short_name(self.config)

    def run(self):
        """
        Build the QU60km mapping file, then partition the mesh.
        """
        check_seaice_model(self.config)
        config = self.config
        logger = self.logger
        short_name = get_mesh_short_name(config)

        self.remapper.src_from_mpas(
            filename='seaice_QU60km_polar.nc', mesh_name='QU60km'
        )
        self.remapper.dst_from_mpas(
            filename='seaice_mesh.nc', mesh_name=short_name
        )
        # builds the mapping file
        super().run()

        check_call(
            [
                'prepare_seaice_partitions',
                '-i',
                'seaice_QU60km_polar.nc',
                '-p',
                'icePresent_QU60km_polar.nc',
                '-m',
                'seaice_mesh.nc',
                '-o',
                '.',
                '-w',
                self.remapper.map_filename,
            ],
            logger,
        )

        section = config['component_inputs']
        cores = self._core_counts()
        logger.info(
            f'Partitioning into {cores[0]} to {cores[-1]} pieces',
        )

        args = [
            'create_seaice_partitions',
            '-m',
            'seaice_mesh.nc',
            '-o',
            '.',
            '-p',
            GRAPH_BASENAME,
            '-g',
            'gpmetis',
            '-n',
        ]
        if section.getboolean('plot_seaice_partitions'):
            args.append('--plotting')

        # the tool takes every core count in one invocation, and will not make
        # a one-piece partition; an empty file is what MPAS reads as "every
        # cell on one task"
        for ncores in cores:
            if ncores == 1:
                with open(f'{GRAPH_BASENAME}.part.1', 'w'):
                    pass
            else:
                args.append(f'{ncores}')

        check_call(args, logger)

    def _core_counts(self):
        """
        The core counts to partition into, from the sea-ice mesh's own cell
        count.
        """
        with xr.open_dataset('seaice_mesh.nc') as ds_mesh:
            ncells = ds_mesh.sizes['nCells']

        section = self.config['component_inputs']
        cores = get_core_list(
            ncells=ncells,
            max_cells_per_core=section.getint('max_cells_per_core'),
            min_cells_per_core=section.getint('min_cells_per_core'),
        )
        if cores[-1] > ncells:
            raise ValueError(
                f'Cannot partition {ncells} cells into {cores[-1]} pieces.'
            )
        return list(cores)
