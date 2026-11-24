import os

from polaris import Step
from polaris.tasks.e3sm.init.topo.remap.prepare import TARGET_SCRIP_FILENAME

#: the weights for remapping from the cubed-sphere grid to the MPAS mesh
MAPPING_FILENAME = 'map_source_to_target_conserve.nc'


class RemapTopoWeightsStep(Step):
    """
    A step for making the weights that remap topography from a cubed-sphere
    grid to a global MPAS base mesh.  Its command is an ``mbtempest``
    launch, or nothing if the prepare step found no remapping to do.

    Attributes
    ----------
    prepare_step : polaris.tasks.e3sm.init.topo.remap.PrepareRemapTopoStep
        The step that makes the SCRIP file for the MPAS mesh

    combine_topo_step : polaris.tasks.e3sm.init.topo.CombineStep
        The step for combining global and Antarctic topography on a cubed
        sphere grid
    """

    def __init__(
        self, component, prepare_step, combine_topo_step, name, subdir
    ):
        """
        Create a new step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        prepare_step : polaris.tasks.e3sm.init.topo.remap.PrepareRemapTopoStep
            The step that makes the SCRIP file for the MPAS mesh

        combine_topo_step : polaris.tasks.e3sm.init.topo.CombineStep
            The step for combining global and Antarctic topography on a cubed
            sphere grid

        name : str
            the name of the step

        subdir : str
            the subdirectory for the step
        """
        super().__init__(
            component, name=name, subdir=subdir, ntasks=1, min_tasks=1
        )
        self.prepare_step = prepare_step
        self.combine_topo_step = combine_topo_step
        # the prepare step makes the SCRIP file only if there is remapping
        # to do, so it is found through the dependency rather than as an
        # input file
        self.add_dependency(prepare_step, name='prepare')

    def setup(self):
        """
        Set up the step in the work directory, including linking input files
        and making the command
        """
        super().setup()
        config = self.config
        section = config['remap_topography']

        combine_topo_step = self.combine_topo_step
        self.add_input_file(
            filename='source.scrip.nc',
            work_dir_target=os.path.join(
                combine_topo_step.path, combine_topo_step.dst_scrip_filename
            ),
        )
        self.add_output_file(filename=MAPPING_FILENAME)

        target_scrip_filename = os.path.join(
            self.base_work_dir, self.prepare_step.path, TARGET_SCRIP_FILENAME
        )
        self.args = [
            [
                'mbtempest',
                '--type',
                '5',
                '--load',
                'source.scrip.nc',
                '--load',
                target_scrip_filename,
                '--file',
                MAPPING_FILENAME,
                '--weights',
                '--gnomonic',
                '--boxeps',
                '1e-9',
            ]
        ]

        self.ntasks = section.getint('ntasks')
        self.min_tasks = section.getint('min_tasks')

    def constrain_resources(self, available_resources):
        """
        Constrain ``cpus_per_task`` and ``ntasks`` based on the number of
        cores available to this step

        Parameters
        ----------
        available_resources : dict
            The total number of cores available to the step
        """
        config = self.config
        section = config['remap_topography']
        self.ntasks = section.getint('ntasks')
        self.min_tasks = section.getint('min_tasks')
        super().constrain_resources(available_resources)

    def runtime_setup(self):
        """
        Launch nothing if the prepare step found no remapping to do
        """
        if not self.dependencies['prepare'].do_remapping:
            self.args = []
            self.outputs = []
