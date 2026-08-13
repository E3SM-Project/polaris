import os
import shutil
from glob import glob

from polaris import Step
from polaris.io import symlink
from polaris.tasks.e3sm.init.component_inputs import names
from polaris.tasks.e3sm.init.component_inputs.ocean_graph_partition import (
    GRAPH_BASENAME as OCEAN_GRAPH_BASENAME,
)
from polaris.tasks.e3sm.init.component_inputs.scrip import ScripStep
from polaris.tasks.e3sm.init.component_inputs.seaice_graph_partition import (
    GRAPH_BASENAME as SEAICE_GRAPH_BASENAME,
)

#: The products every task stages, whichever model it is for: the base mesh
#: belongs to the ocean, sea-ice, land and river components equally.
SHARED_PRODUCTS = ('staged_base_mesh', 'scrip')

#: The products each target adds to those.
TARGET_PRODUCTS: dict[str, tuple[str, ...]] = {
    'ocean': (
        'ocean_mesh',
        'ocean_initial_condition',
        'ocean_graph_partition',
        'ocean_moc_masks',
    ),
    'seaice': (
        'seaice_mesh',
        'seaice_initial_condition',
        'seaice_graph_partition',
    ),
}
TARGET_PRODUCTS['all'] = TARGET_PRODUCTS['ocean'] + TARGET_PRODUCTS['seaice']


class AssembleStep(Step):
    """
    A step for materializing the staged tree of component input files.

    Compass scatters ``symlink()`` calls through the product steps, which is
    what makes its ``assembled_files`` tree hard to reason about: to know what
    is in it you have to read every step.  Here the product steps write only
    their own outputs and this step builds the tree, so the layout lives in
    one place -- :py:mod:`~polaris.tasks.e3sm.init.component_inputs.names`
    for the paths, and this step for what goes where.

    One assembly step per task, because the three tasks stage different sets.

    Attributes
    ----------
    target : {'ocean', 'seaice', 'all'}
        Which products this step stages.

    product_steps : dict of {str: polaris.Step}
        The steps whose outputs are staged, keyed as
        :py:func:`~polaris.tasks.e3sm.init.component_inputs.steps.get_component_inputs_steps`
        keys them.
    """

    #: The cull step's land mesh, staged as it was written.  It gets no step
    #: of its own because there is nothing to compute or restamp: unlike the
    #: SCRIP files it carries no mesh name, and unlike the ocean mesh it needs
    #: no vertical coordinate.
    LAND_MESH_FILENAME = 'culled_land_mesh.nc'

    def __init__(
        self,
        component,
        subdir,
        target,
        product_steps,
        cull_mesh_step,
        name=None,
    ):
        """
        Create a new step.

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to.

        subdir : str
            The subdirectory for the step.

        target : {'ocean', 'seaice', 'all'}
            Which products to stage.

        product_steps : dict of {str: polaris.Step}
            All component-input steps, from which this picks what ``target``
            calls for.

        cull_mesh_step : polaris.tasks.e3sm.init.topo.cull.cull.CullMeshStep
            The step that wrote the culled land mesh.

        name : str, optional
            The name of the step.
        """
        if target not in TARGET_PRODUCTS:
            raise ValueError(
                f'Unknown assembly target {target!r}.  Expected one of '
                f'{", ".join(sorted(TARGET_PRODUCTS))}.'
            )
        super().__init__(
            component=component,
            name=name or f'assemble_{target}',
            subdir=subdir,
        )
        self.target = target

        wanted = SHARED_PRODUCTS + TARGET_PRODUCTS[target]
        self.product_steps = {
            key: product_steps[key] for key in wanted if key in product_steps
        }

        self.add_input_file(filename='README', package=names.__package__)
        self.add_input_file(
            filename=self.LAND_MESH_FILENAME,
            work_dir_target=os.path.join(
                cull_mesh_step.path, self.LAND_MESH_FILENAME
            ),
        )

        for key, step in self.product_steps.items():
            if key.endswith('graph_partition'):
                # the partitions are named for core counts that follow from a
                # cell count not known until the mesh exists, so they cannot
                # be declared here; they are found at run time instead
                continue
            if key == 'ocean_moc_masks':
                # this step declares its outputs in setup(), which has not run
                # yet, so name the one file that is staged rather than reading
                # an outputs list that is still empty
                self.add_input_file(
                    filename=f'{key}__{step.output_filename}',
                    work_dir_target=os.path.join(
                        step.path, step.output_filename
                    ),
                )
                continue
            for output in step.outputs:
                self.add_input_file(
                    filename=f'{key}__{output}',
                    work_dir_target=os.path.join(step.path, output),
                )

    def run(self):
        """
        Build the staged tree, from empty.

        The tree is deleted first so that it describes this assembly and not
        the union of every assembly ever run here.  Staging only ever adds
        links, so without this a changed creation date, mesh short name or
        product set leaves the previous names behind -- still resolving, and
        now pointing at newer content.  Rebuilding is a few hundred symlinks,
        which is cheap next to being unable to trust what is in the tree.
        """
        super().run()
        config = self.config
        short_name = names.get_mesh_short_name(config)
        creation_date = names.get_creation_date(config)

        if os.path.exists(names.ASSEMBLED_FILES):
            shutil.rmtree(names.ASSEMBLED_FILES)

        self._stage('README', 'README')

        self._stage(
            'staged_base_mesh__'
            + self.product_steps['staged_base_mesh'].output_filename,
            names.base_mesh_path(short_name, creation_date),
        )

        for region in names.SCRIP_REGIONS:
            self._stage(
                f'scrip__{ScripStep.scrip_filename(region)}',
                names.scrip_path(short_name, creation_date, region),
            )

        # the land mesh belongs to the shared set: it describes a domain of
        # the unified mesh, not something one component runs with
        self._stage(
            self.LAND_MESH_FILENAME,
            names.culled_mesh_path(short_name, creation_date, 'land'),
        )

        if 'ocean_mesh' in self.product_steps:
            # the same SCRIP files as above, in the second place developers
            # look for them, named as they read in an ocean directory
            for region in names.OCEAN_SCRIP_REGIONS:
                self._stage(
                    f'scrip__{ScripStep.scrip_filename(region)}',
                    names.ocean_scrip_path(short_name, creation_date, region),
                )

            self._stage(
                'ocean_mesh__ocean_mesh.nc',
                names.culled_mesh_path(short_name, creation_date, 'ocean'),
            )
            self._stage(
                'ocean_initial_condition__ocean_initial_condition.nc',
                names.ocean_initial_condition_path(short_name, creation_date),
            )
            self._stage_partitions(
                step=self.product_steps['ocean_graph_partition'],
                basename=OCEAN_GRAPH_BASENAME,
                path_func=names.ocean_partition_path,
                short_name=short_name,
                creation_date=creation_date,
            )
            moc_masks = self.product_steps['ocean_moc_masks']
            self._stage(
                f'ocean_moc_masks__{moc_masks.output_filename}',
                names.ocean_moc_masks_path(
                    short_name, creation_date, moc_masks.features_date
                ),
            )

        if 'seaice_mesh' in self.product_steps:
            self._stage(
                'seaice_mesh__seaice_mesh.nc',
                names.seaice_mesh_path(short_name, creation_date),
            )
            self._stage(
                'seaice_initial_condition__seaice_initial_condition.nc',
                names.seaice_initial_condition_path(short_name, creation_date),
            )
            self._stage_partitions(
                step=self.product_steps['seaice_graph_partition'],
                basename=SEAICE_GRAPH_BASENAME,
                path_func=names.seaice_partition_path,
                short_name=short_name,
                creation_date=creation_date,
            )

    def _stage(self, source, staged_path):
        """
        Link one product into the assembled tree at its E3SM-facing path.
        """
        destination = os.path.join(names.ASSEMBLED_FILES, staged_path)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        symlink(os.path.abspath(source), destination)

    def _stage_partitions(
        self, step, basename, path_func, short_name, creation_date
    ):
        """
        Link every partition the given step produced.

        Found by listing rather than by recomputing the core list, so that the
        staged tree describes what was actually built.
        """
        relative = os.path.relpath(step.path, self.path)
        step_dir = os.path.normpath(os.path.join(self.work_dir, relative))

        found = sorted(glob(os.path.join(step_dir, f'{basename}.part.*')))
        if not found:
            raise FileNotFoundError(
                f'{step.name} produced no partition files in {step_dir}.'
            )
        for source in found:
            ncores = int(os.path.basename(source).rsplit('.', 1)[-1])
            self._stage(
                source,
                path_func(short_name, creation_date, ncores),
            )
