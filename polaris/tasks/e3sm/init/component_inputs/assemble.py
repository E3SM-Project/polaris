import os
from functools import partial

from polaris.e3sm.init import inputdata
from polaris.e3sm.init.assemble import AssembleStep
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

#: The ocean products each ocean model reads.  Omega partitions its mesh at
#: run time and does not yet read region masks, so it gets no partitions and
#: no MOC masks.  The culled ocean mesh is made from MPAS-Ocean's initial
#: state, so only MPAS-Ocean's tasks stage it.
OCEAN_PRODUCTS: dict[str, tuple[str, ...]] = {
    'mpas-ocean': (
        'ocean_mesh',
        'ocean_initial_condition',
        'ocean_graph_partition',
        'ocean_moc_masks',
    ),
    'omega': ('ocean_initial_condition',),
}

#: The sea-ice products.  ``seaice_mesh`` is not among them: the step exists
#: because the partition steps read its output, but the mesh itself is the
#: culled ocean mesh under another name, so staging it would put a second
#: copy of :py:func:`~...names.culled_mesh_path`'s ocean mesh in the tree.
#: MPAS-Seaice reads its mesh from the initial condition.
SEAICE_PRODUCTS = ('seaice_initial_condition', 'seaice_graph_partition')

#: Which products each target stages besides the shared ones
TARGETS = ('ocean', 'seaice', 'all')


def target_products(target, model):
    """
    The products a target stages for an ocean model, besides the shared ones.

    Parameters
    ----------
    target : {'ocean', 'seaice', 'all'}
        Which products to stage.

    model : {'mpas-ocean', 'omega'} or None
        The ocean model, for the ``ocean`` and ``all`` targets only.

    Returns
    -------
    tuple of str
        The products.

    Raises
    ------
    ValueError
        If ``target`` or ``model`` is unknown, a model is missing for a target
        with ocean products, or one is given for ``seaice``.
    """
    if target not in TARGETS:
        raise ValueError(
            f'Unknown component-inputs target {target!r}.  Expected one of '
            f'{", ".join(TARGETS)}.'
        )
    if target == 'seaice':
        if model is not None:
            raise ValueError(
                f'The seaice target stages no ocean products, so it takes no '
                f'ocean model, but {model!r} was given.'
            )
        return SEAICE_PRODUCTS
    if model not in OCEAN_PRODUCTS:
        raise ValueError(
            f'The {target} target needs an ocean model, one of '
            f'{", ".join(OCEAN_PRODUCTS)}, not {model!r}.'
        )
    products = OCEAN_PRODUCTS[model]
    if target == 'all':
        products = products + SEAICE_PRODUCTS
    return products


class ComponentInputsAssembleStep(AssembleStep):
    """
    A step for materializing the staged tree of component input files.

    Compass scatters ``symlink()`` calls through the product steps, which is
    what makes its ``assembled_files`` tree hard to reason about: to know what
    is in it you have to read every step.  Here the product steps write only
    their own outputs and this step builds the tree, so the layout lives in
    one place -- :py:mod:`polaris.e3sm.init.inputdata` and
    :py:mod:`~polaris.tasks.e3sm.init.component_inputs.names` for the paths,
    and this step for what goes where.

    One assembly step per task, because each task stages a different set.

    Model-neutral products are stamped with the mesh's creation date and each
    model's initial condition with the ocean creation date of its own, so
    that a second model's products can join a mesh's tree without renaming
    what is already staged.

    Attributes
    ----------
    target : {'ocean', 'seaice', 'all'}
        Which products this step stages.

    model : {'mpas-ocean', 'omega'} or None
        The ocean model whose products it stages.

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
        model,
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

        model : {'mpas-ocean', 'omega'} or None
            The ocean model whose products to stage, for the ``ocean`` and
            ``all`` targets.

        product_steps : dict of {str: polaris.Step}
            All component-input steps, from which this picks what ``target``
            calls for.

        cull_mesh_step : polaris.tasks.e3sm.init.topo.cull.cull.CullMeshStep
            The step that wrote the culled land mesh.

        name : str, optional
            The name of the step.
        """
        products = target_products(target, model)
        super().__init__(
            component=component,
            name=name or f'assemble_{target}',
            subdir=subdir,
            readme_package=names.__package__,
        )
        self.target = target
        self.model = model

        wanted = SHARED_PRODUCTS + products
        self.product_steps = {
            key: product_steps[key] for key in wanted if key in product_steps
        }

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
                # be declared here; they are found at run time instead.  With
                # no input file to order the two, a parallel run needs the
                # dependency, or it assembles before any partition exists.
                self.add_dependency(step, name=key)
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
        """
        super().run()
        config = self.config
        short_name = names.get_mesh_short_name(config)
        creation_date = inputdata.get_creation_date(config, 'component_inputs')
        grid = names.ocean_grid_name(short_name)
        model = self.model

        self.stage(
            'staged_base_mesh__'
            + self.product_steps['staged_base_mesh'].output_filename,
            names.base_mesh_path(short_name, creation_date),
        )

        for region in names.SCRIP_REGIONS:
            self.stage(
                f'scrip__{ScripStep.scrip_filename(region)}',
                names.scrip_path(short_name, creation_date, region),
            )

        # the land mesh belongs to the shared set: it describes a domain of
        # the unified mesh, not something one component runs with
        self.stage(
            self.LAND_MESH_FILENAME,
            names.culled_mesh_path(short_name, creation_date, 'land'),
        )

        if model is not None:
            ocean_date = inputdata.get_creation_date(
                config, 'component_inputs', 'ocean_creation_date'
            )
            # the same SCRIP files as above, in the second place developers
            # look for them, named as they read in an ocean directory
            for region in names.OCEAN_SCRIP_REGIONS:
                self.stage(
                    f'scrip__{ScripStep.scrip_filename(region)}',
                    names.ocean_scrip_path(
                        short_name, creation_date, region, model
                    ),
                )
            initial_condition = (
                'ocean_initial_condition__ocean_initial_condition.nc'
            )
            if model == 'omega':
                self.stage(
                    initial_condition,
                    inputdata.omega_initial_condition_path(grid, ocean_date),
                )
            else:
                self.stage(
                    initial_condition,
                    inputdata.ocean_initial_condition_path(grid, ocean_date),
                )
                self._stage_mpas_ocean_products(
                    short_name, creation_date, grid
                )

        if 'seaice_initial_condition' in self.product_steps:
            self.stage(
                'seaice_initial_condition__seaice_initial_condition.nc',
                inputdata.seaice_initial_condition_path(grid, creation_date),
            )
            self.stage_partitions(
                step=self.product_steps['seaice_graph_partition'],
                basename=SEAICE_GRAPH_BASENAME,
                path_func=partial(
                    inputdata.seaice_partition_path, grid, creation_date
                ),
            )

    def _stage_mpas_ocean_products(self, short_name, creation_date, grid):
        """
        Stage the products only MPAS-Ocean reads, and the culled ocean mesh,
        which is made from its initial state.  All are stamped with the mesh's
        creation date, since none of them depends on the ocean state.
        """
        self.stage(
            'ocean_mesh__ocean_mesh.nc',
            names.culled_mesh_path(short_name, creation_date, 'ocean'),
        )
        ocean_partitions = self.product_steps['ocean_graph_partition']
        self.stage_partitions(
            step=ocean_partitions,
            basename=OCEAN_GRAPH_BASENAME,
            path_func=partial(
                inputdata.ocean_partition_path, grid, creation_date
            ),
        )
        partition_dir = self.step_dir(ocean_partitions)
        self.stage(
            os.path.join(partition_dir, OCEAN_GRAPH_BASENAME),
            inputdata.ocean_graph_path(grid, creation_date),
        )
        moc_masks = self.product_steps['ocean_moc_masks']
        self.stage(
            f'ocean_moc_masks__{moc_masks.output_filename}',
            names.ocean_moc_masks_path(
                short_name, creation_date, moc_masks.features_date
            ),
        )
