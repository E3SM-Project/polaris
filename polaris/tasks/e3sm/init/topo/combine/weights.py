import os

from polaris.step import Step
from polaris.tasks.e3sm.init.topo.combine.files import get_combine_files


class CombineWeightsStep(Step):
    """
    A step for making the weights that remap each tile of the global dataset
    and the Antarctic dataset to the target grid of combined topography.
    Its command is one ``ESMF_RegridWeightGen`` launch per tile and one for
    the Antarctic dataset.

    Attributes
    ----------
    prepare_step : polaris.tasks.e3sm.init.topo.combine.PrepareCombineStep
        The step that makes the tiles and SCRIP files
    """

    def __init__(self, component, subdir, name, prepare_step):
        """
        Create a new step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory within the component's work directory

        name : str
            The name of the step

        prepare_step : polaris.tasks.e3sm.init.topo.combine.PrepareCombineStep
            The step that makes the tiles and SCRIP files
        """
        super().__init__(
            component=component,
            name=name,
            subdir=subdir,
            ntasks=None,
            min_tasks=None,
        )
        self.prepare_step = prepare_step

    def setup(self):
        """
        Set up the step in the work directory, including linking the tiles
        and SCRIP files and making the commands
        """
        super().setup()
        config = self.config
        section = config['combine_topo']
        method = section.get('method')
        files = get_combine_files(config)

        sources = [tile.source for tile in files.tiles]
        sources.extend([files.target_scrip, files.antarctic_scrip])
        for filename in sources:
            self.add_input_file(
                filename=filename,
                work_dir_target=os.path.join(self.prepare_step.path, filename),
            )

        self.args = list()
        for tile in files.tiles:
            self.args.append(
                _get_esmf_args(
                    src_filename=tile.source,
                    dst_filename=files.target_scrip,
                    weight_filename=tile.mapping,
                    method=method,
                )
            )
            self.add_output_file(filename=tile.mapping)
        self.args.append(
            _get_esmf_args(
                src_filename=files.antarctic_scrip,
                dst_filename=files.target_scrip,
                weight_filename=files.antarctic_mapping,
                method=method,
            )
        )
        self.add_output_file(filename=files.antarctic_mapping)

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
        self.ntasks = config.getint('combine_topo', 'ntasks')
        self.min_tasks = config.getint('combine_topo', 'min_tasks')
        super().constrain_resources(available_resources)


def _get_esmf_args(src_filename, dst_filename, weight_filename, method):
    """
    Get the command for making a weights file for a regional source grid
    """
    return [
        'ESMF_RegridWeightGen',
        '--source',
        src_filename,
        '--destination',
        dst_filename,
        '--weight',
        weight_filename,
        '--method',
        method,
        '--netcdf4',
        '--src_regional',
        '--ignore_unmapped',
    ]
