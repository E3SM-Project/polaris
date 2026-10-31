import os
from functools import partial

from polaris.e3sm.init import inputdata
from polaris.e3sm.init.assemble import AssembleStep
from polaris.tasks.e3sm.init.misomip import names
from polaris.tasks.e3sm.init.misomip.case_config import CASE_CONFIG_FILES
from polaris.tasks.e3sm.init.misomip.maps import MAPS

#: The file each product step writes that is staged, keyed as
#: :py:class:`MisomipAssembleStep` keys the steps.  The maps, in
#: :py:data:`~polaris.tasks.e3sm.init.misomip.maps.MAPS`, each stage
#: ``map.nc``.
PRODUCT_FILES = {
    'ocean_mesh': 'ocean_scrip.nc',
    'landice_mesh': 'landice_scrip.nc',
    'ocean_initial_condition': 'ocean_initial_condition.nc',
    'ocean_forcing': 'forcing.nc',
    'landice_init': 'landice_init.nc',
    'landice_data': 'landice_datamode.nc',
}

#: The step that writes the case configuration, whose files are in
#: :py:data:`~polaris.tasks.e3sm.init.misomip.case_config.CASE_CONFIG_FILES`
CASE_CONFIG = 'case_config'

#: The steps whose partitions are staged, and the stem of their files
PARTITION_PRODUCTS = {
    'ocean_partitions': 'mpas-o.graph.info',
    'landice_partitions': 'mpasli.graph.info',
}


class MisomipAssembleStep(AssembleStep):
    """
    A step for materializing the staged tree of E3SM's inputs for one
    MISOMIP experiment

    Attributes
    ----------
    experiment : str
        The experiment

    product_steps : dict of str to polaris.Step
        The steps whose outputs are staged, keyed as in
        :py:data:`PRODUCT_FILES` and :py:data:`PARTITION_PRODUCTS`, with
        each map's step keyed ``maps/<map name>`` and the case
        configuration's :py:data:`CASE_CONFIG`
    """

    def __init__(self, component, subdir, experiment, product_steps):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory for the step

        experiment : str
            The experiment

        product_steps : dict of str to polaris.Step
            The steps whose outputs are staged.  An experiment stages only
            the products it has: IceOcean1ra, which continues from
            IceOcean1r's E3SM restart, has no initial conditions.
        """
        super().__init__(
            component=component,
            name='assemble',
            subdir=subdir,
            readme_package=names.__package__,
        )
        self.experiment = experiment
        self.product_steps = product_steps
        for key, step in product_steps.items():
            if key in PARTITION_PRODUCTS:
                # named for core counts that follow from a cell count not
                # known until the mesh exists, so found at run time
                self.add_dependency(step, name=key)
                continue
            if key == CASE_CONFIG:
                filenames = CASE_CONFIG_FILES
            else:
                filenames = [_get_product_file(key)]
            for filename in filenames:
                self.add_input_file(
                    filename=_get_staged_source(key, filename),
                    work_dir_target=os.path.join(step.path, filename),
                )

    def run(self):
        """
        Build the staged tree, from empty
        """
        super().run()
        config = self.config
        experiment = self.experiment
        grids = names.get_grid_names(config)
        ocean = grids['ocean']
        landice = grids['landice']
        date = inputdata.get_creation_date(config, names.INPUTS_SECTION)

        paths = {
            'ocean_mesh': names.ocean_scrip_path(ocean, date),
            'landice_mesh': names.landice_scrip_path(landice, date),
            'ocean_initial_condition': names.ocean_initial_condition_path(
                ocean, experiment, date
            ),
            'ocean_forcing': names.ocean_forcing_path(ocean, experiment, date),
            'landice_init': names.landice_initial_condition_path(
                landice, experiment, date
            ),
            'landice_data': names.landice_data_mode_path(
                landice, experiment, date
            ),
        }
        for map_name, (src, dst, _) in MAPS.items():
            method = map_name.rsplit('_', 1)[-1]
            paths[f'maps/{map_name}'] = names.map_path(
                grids[src], grids[dst], method, date
            )

        partition_paths = {
            'ocean_partitions': partial(
                inputdata.ocean_partition_path, ocean, date
            ),
            'landice_partitions': partial(
                names.landice_partition_path, landice, date
            ),
        }

        for key, step in self.product_steps.items():
            if key in PARTITION_PRODUCTS:
                self.stage_partitions(
                    step=step,
                    basename=PARTITION_PRODUCTS[key],
                    path_func=partition_paths[key],
                )
            elif key == CASE_CONFIG:
                case_dir = names.case_config_dir(experiment)
                for filename in CASE_CONFIG_FILES:
                    self.stage(
                        _get_staged_source(key, filename),
                        f'{case_dir}/{filename}',
                    )
            else:
                self.stage(_get_staged_source(key), paths[key])


def _get_product_file(key):
    """
    The file a product step writes that is staged
    """
    if key.startswith('maps/'):
        return 'map.nc'
    return PRODUCT_FILES[key]


def _get_staged_source(key, filename=None):
    """
    The name of a product in the assembly step's work directory
    """
    if filename is None:
        filename = _get_product_file(key)
    return f'{key.replace("/", "__")}__{filename}'
