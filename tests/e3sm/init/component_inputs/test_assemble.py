import logging
import os

import pytest
from geometric_features.aggregation import get_aggregator_by_name

from polaris.e3sm.init import inputdata
from polaris.e3sm.init.assemble import SYNC_SCRIPT
from polaris.e3sm.init.inputdata import ASSEMBLED_FILES
from polaris.tasks.e3sm.init import e3sm_init
from polaris.tasks.e3sm.init.component_inputs import names
from polaris.tasks.e3sm.init.component_inputs.assemble import (
    SHARED_PRODUCTS,
    target_products,
)
from polaris.tasks.e3sm.init.component_inputs.steps import (
    get_component_inputs_steps,
)
from polaris.tasks.e3sm.init.component_inputs.tasks import (
    add_component_inputs_tasks,
)
from polaris.tasks.mesh import mesh as mesh_component
from polaris.tasks.mesh.spherical.feature_masks.moc import MOC_MASK_GROUP
from polaris.tasks.ocean import ocean

MESH_NAME = 'u-oi30-lr10'
SHORT_NAME = 'u02-oi30-lr10'
# E3SM's names for the mesh's directory and its ocean and sea-ice grid
MESH_ID = 'u02'
OCEAN_GRID = 'u02-oi30'
CREATION_DATE = '20250101'
# a date of its own, so the tests can tell which products carry which
OCEAN_DATE = '20250303'

# every target, with the ocean model its tasks are built for
CASES = [
    ('ocean', 'mpas-ocean'),
    ('seaice', None),
    ('all', 'mpas-ocean'),
    ('ocean', 'omega'),
    ('all', 'omega'),
]

# read from the aggregation rather than hard-coded, since the whole point of
# carrying this date separately is that it can change without us
FEATURES_DATE = get_aggregator_by_name(MOC_MASK_GROUP)[2]

LOGGER = logging.getLogger('test_assemble')

# the partitions the fake graph steps are given, chosen so the staged names
# are distinguishable from each other
NCORES = [1, 8, 128]


def test_the_seaice_task_never_builds_the_ocean_chain():
    """
    The strongest form of D7: not that the sea-ice steps avoid the ocean, but
    that setting up the sea-ice task does not create the dynamic-adjustment
    chain at all.  A sea-ice task cannot wait on a model run that was never
    built.
    """
    _reset_shared_components()
    steps, _ = get_component_inputs_steps(mesh_name=MESH_NAME, target='seaice')

    assert not [
        name for name, step in steps.items() if step.path.startswith('ocean/')
    ]
    assert not ocean.steps


def test_the_ocean_task_does_build_the_ocean_chain():
    """The counterpart, so the test above cannot pass by building nothing."""
    _reset_shared_components()
    steps, _ = get_component_inputs_steps(
        mesh_name=MESH_NAME, target='ocean', model='mpas-ocean'
    )

    assert [
        name for name, step in steps.items() if step.path.startswith('ocean/')
    ]
    assert 'simulation' in steps


@pytest.mark.parametrize(('target', 'model'), CASES)
def test_each_target_stages_its_own_products(target, model):
    _reset_shared_components()
    steps, _ = get_component_inputs_steps(
        mesh_name=MESH_NAME, target=target, model=model
    )
    assemble = steps[f'assemble_{target}']

    expected = set(SHARED_PRODUCTS) | set(target_products(target, model))
    assert set(assemble.product_steps) == expected


@pytest.mark.parametrize(
    ('target', 'model'),
    [case for case in CASES if case != ('ocean', 'omega')],
)
def test_assembly_waits_for_the_partition_steps(target, model):
    """
    The partitions cannot be declared as inputs, so without a dependency a
    parallel run assembles while the partition steps are still running.
    """
    _reset_shared_components()
    steps, _ = get_component_inputs_steps(
        mesh_name=MESH_NAME, target=target, model=model
    )
    assemble = steps[f'assemble_{target}']

    partition_keys = [
        key
        for key in target_products(target, model)
        if key.endswith('partition')
    ]
    assert partition_keys
    for key in partition_keys:
        assert assemble.dependencies[key] is steps[key]


def test_an_unknown_target_is_rejected():
    _reset_shared_components()
    with pytest.raises(ValueError, match='land'):
        get_component_inputs_steps(
            mesh_name=MESH_NAME, target='land', model='mpas-ocean'
        )


@pytest.mark.parametrize('target', ['ocean', 'all'])
def test_a_target_with_ocean_products_needs_a_model(target):
    with pytest.raises(ValueError, match='needs an ocean model'):
        target_products(target, None)


def test_the_seaice_target_takes_no_model():
    with pytest.raises(ValueError, match='takes no ocean model'):
        target_products('seaice', 'omega')


def test_the_tasks_live_under_a_directory_of_their_own():
    """
    The tasks share most of their steps, so a task subdirectory could
    otherwise collide with a step subdirectory of the same name.  Each ocean
    model's tasks have a directory of their own, so that both models' can be
    set up in one work directory.
    """
    _reset_shared_components()
    add_component_inputs_tasks(component=e3sm_init)

    tasks = f'{MESH_NAME}/component_inputs/tasks'
    subdirs = [f'{tasks}/seaice'] + [
        f'{tasks}/{model}/{target}'
        for model in ['mpas-ocean', 'omega']
        for target in ['ocean', 'all']
    ]
    assert sorted(
        subdir for subdir in e3sm_init.tasks if subdir.startswith(f'{tasks}/')
    ) == sorted(subdirs)
    # no step lives under tasks/
    assert not [s for s in e3sm_init.steps if s.startswith(f'{tasks}/')]


def test_the_creation_dates_are_fixed_at_setup(monkeypatch):
    """
    Filled in during configure so they land in the work directory's config; a
    re-run then keeps the dates it was set up with rather than renaming every
    staged file to today's.
    """
    _reset_shared_components()
    add_component_inputs_tasks(component=e3sm_init)
    tasks = f'{MESH_NAME}/component_inputs/tasks'
    task = e3sm_init.tasks[f'{tasks}/mpas-ocean/all']
    monkeypatch.setattr(ocean, 'model', 'mpas-ocean')

    first = dict()
    for option in ['creation_date', 'ocean_creation_date']:
        task.config.set('component_inputs', option, '')
    task.configure()
    for option in ['creation_date', 'ocean_creation_date']:
        first[option] = task.config.get('component_inputs', option)
        assert first[option] != ''
    task.configure()
    for option in ['creation_date', 'ocean_creation_date']:
        assert task.config.get('component_inputs', option) == first[option]


@pytest.mark.parametrize(('target', 'model'), CASES)
def test_every_product_lands_at_its_e3sm_path(tmp_path, target, model):
    """
    The staged layout, checked by running the step and listing what it built.
    The model-neutral products carry the mesh's date and the ocean initial
    condition the model's own.
    """
    staged = _run_assemble(tmp_path, target, model)

    mesh_dir = f'inputdata/share/meshes/mpas/unified/{MESH_ID}'
    expected = {
        'README',
        f'{mesh_dir}/{SHORT_NAME}.base.{CREATION_DATE}.nc',
        f'{mesh_dir}/{SHORT_NAME}.ocean.scrip.{CREATION_DATE}.nc',
        f'{mesh_dir}/{SHORT_NAME}.ocean_no_cavities.scrip.{CREATION_DATE}.nc',
        f'{mesh_dir}/{SHORT_NAME}.land.scrip.{CREATION_DATE}.nc',
        f'{mesh_dir}/{SHORT_NAME}.land.{CREATION_DATE}.nc',
    }
    products = target_products(target, model)
    if model == 'omega':
        ocn = f'inputdata/ocn/omega/{OCEAN_GRID}'
        expected |= {
            f'{ocn}/omega.{OCEAN_GRID}.{OCEAN_DATE}.nc',
            f'{ocn}/{SHORT_NAME}.scrip.{CREATION_DATE}.nc',
            f'{ocn}/{SHORT_NAME}.no_cavities.scrip.{CREATION_DATE}.nc',
        }
    if 'ocean_mesh' in products:
        ocn = f'inputdata/ocn/mpas-o/{OCEAN_GRID}'
        expected |= {
            f'{mesh_dir}/{SHORT_NAME}.ocean.{CREATION_DATE}.nc',
            f'{ocn}/mpaso.{OCEAN_GRID}.{OCEAN_DATE}.nc',
            f'{ocn}/{SHORT_NAME}.mocBasinsAndTransects'
            f'{FEATURES_DATE}.{CREATION_DATE}.nc',
            f'{ocn}/{SHORT_NAME}.scrip.{CREATION_DATE}.nc',
            f'{ocn}/{SHORT_NAME}.no_cavities.scrip.{CREATION_DATE}.nc',
            # the graph the partitions were made from, as on the server
            f'{ocn}/partitions/mpas-o.graph.info.{CREATION_DATE}',
        } | {
            f'{ocn}/partitions/mpas-o.graph.info.{CREATION_DATE}.part.{n}'
            for n in NCORES
        }
    if 'seaice_initial_condition' in products:
        ice = f'inputdata/ice/mpas-seaice/{OCEAN_GRID}'
        expected |= {
            f'{ice}/mpassi.{OCEAN_GRID}.{CREATION_DATE}.nc',
        } | {
            f'{ice}/partitions/mpas-seaice.graph.info.{CREATION_DATE}.part.{n}'
            for n in NCORES
        }

    assert staged == expected


def test_the_staged_files_point_at_the_products(tmp_path):
    """
    Links, not copies, and each one resolving to the file the product step
    actually wrote.
    """
    _run_assemble(tmp_path, 'all')
    root = _assembly_dir(tmp_path, 'all') / ASSEMBLED_FILES

    mesh = (
        root
        / 'inputdata/ocn/mpas-o'
        / OCEAN_GRID
        / f'mpaso.{OCEAN_GRID}.{OCEAN_DATE}.nc'
    )
    assert mesh.is_symlink()
    assert os.path.realpath(mesh).endswith(
        'ocean_initial_condition__ocean_initial_condition.nc'
    )


def test_a_partition_step_that_produced_nothing_is_an_error(tmp_path):
    """
    The partitions are found by listing rather than declared, so an empty
    directory would otherwise stage a silently incomplete tree.
    """
    with pytest.raises(FileNotFoundError, match='no partition files'):
        _run_assemble(tmp_path, 'ocean', 'mpas-ocean', partitions=[])


def _run_assemble(
    tmp_path,
    target,
    model='mpas-ocean',
    partitions=None,
    creation_date=CREATION_DATE,
):
    """
    Run the assembly step over fake products, and list what it staged.

    The step reads its inputs by local filename, so the products only have to
    exist under the names the step declared for them.
    """
    if partitions is None:
        partitions = NCORES

    _reset_shared_components()
    steps, config = get_component_inputs_steps(
        mesh_name=MESH_NAME, target=target, model=model
    )
    step = steps[f'assemble_{target}']

    config.set('component_inputs', 'creation_date', creation_date)
    config.set('component_inputs', 'ocean_creation_date', OCEAN_DATE)
    step.config = config
    step.logger = LOGGER
    step.work_dir = str(_assembly_dir(tmp_path, target, model))
    os.makedirs(step.work_dir, exist_ok=True)

    # the declared inputs, as the step will look for them
    for entry in step.input_data:
        path = os.path.join(step.work_dir, entry['filename'])
        # dependencies are declared as pickles in a subdirectory
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as handle:
            handle.write(entry['filename'])

    # and the partitions, which are found rather than declared
    for key, basename in [
        ('ocean_graph_partition', 'mpas-o.graph.info'),
        ('seaice_graph_partition', 'mpas-seaice.graph.info'),
    ]:
        if key not in step.product_steps:
            continue
        part_dir = tmp_path / key
        part_dir.mkdir(exist_ok=True)
        # the partition step copies its graph to the basename it partitions
        (part_dir / basename).write_text('')
        for ncores in partitions:
            (part_dir / f'{basename}.part.{ncores}').write_text('')

    cwd = os.getcwd()
    try:
        os.chdir(step.work_dir)
        step.run()
    finally:
        os.chdir(cwd)

    root = os.path.join(step.work_dir, ASSEMBLED_FILES)
    staged = set()
    for dirpath, _, filenames in os.walk(root):
        for filename in filenames:
            full = os.path.join(dirpath, filename)
            staged.add(os.path.relpath(full, root))
    return staged


def _assembly_dir(tmp_path, target, model='mpas-ocean'):
    """
    Where a test runs an assembly step, laid out below ``tmp_path`` as the
    step is below the mesh's component-inputs directory, so that the step
    finds the partition steps' directories at ``tmp_path/<step>``.
    """
    if model is None:
        return tmp_path / 'assemble' / target
    return tmp_path / model / 'assemble' / target


def _reset_shared_components():
    for component in [e3sm_init, mesh_component, ocean]:
        component.tasks.clear()
        component.steps.clear()
        component.configs.clear()


def test_the_tree_describes_one_assembly_not_every_assembly(tmp_path):
    """
    Staging only ever adds links, so without clearing first, a second run
    under a different creation date leaves the first run's names in place --
    still resolving, now pointing at newer content.  That is how the oi240
    test tree ended up holding 20260811 and 20260812 side by side.
    """
    first = _run_assemble(tmp_path, 'all', creation_date='20250101')
    assert any('.20250101.' in name for name in first)

    second = _run_assemble(tmp_path, 'all', creation_date='20250202')

    assert any('.20250202.' in name for name in second)
    stale = sorted(name for name in second if '.20250101.' in name)
    assert stale == [], f'{len(stale)} file(s) left from the earlier date'


def test_the_meshes_are_staged_beside_the_base_mesh(tmp_path):
    """
    Not under a component's own directory.  A culled mesh describes a domain
    of the unified mesh rather than a file one component reads at run time,
    which is the same argument that puts the base mesh in share/meshes.  An
    earlier version staged the ocean mesh under ocn/mpas-o/, where Compass
    never put it and where E3SM does not look for it.
    """
    staged = _run_assemble(tmp_path, 'all')

    mesh_dir = f'inputdata/share/meshes/mpas/unified/{MESH_ID}'
    assert f'{mesh_dir}/{SHORT_NAME}.ocean.{CREATION_DATE}.nc' in staged
    assert f'{mesh_dir}/{SHORT_NAME}.land.{CREATION_DATE}.nc' in staged

    under_ocn = [
        name
        for name in staged
        if name.startswith(f'inputdata/ocn/mpas-o/{OCEAN_GRID}/')
        and 'partitions/' not in name
    ]
    ocn = f'inputdata/ocn/mpas-o/{OCEAN_GRID}'
    assert set(under_ocn) == {
        f'{ocn}/mpaso.{OCEAN_GRID}.{OCEAN_DATE}.nc',
        f'{ocn}/{SHORT_NAME}.mocBasinsAndTransects'
        f'{FEATURES_DATE}.{CREATION_DATE}.nc',
        f'{ocn}/{SHORT_NAME}.scrip.{CREATION_DATE}.nc',
        f'{ocn}/{SHORT_NAME}.no_cavities.scrip.{CREATION_DATE}.nc',
    }


def test_the_shared_mesh_files_are_under_a_per_mesh_subdirectory(tmp_path):
    """
    Every unified mesh gets its own subdirectory of
    share/meshes/mpas/unified/, named for the ID that leads its E3SM short
    name, as E3SM and the inputdata server name them, and nothing is
    staged directly in the shared directory.  One mesh contributes half a
    dozen files, so a flat directory holding several meshes gives no way to
    see which files belong together or to copy one mesh's as a unit.
    """
    staged = _run_assemble(tmp_path, 'all')

    unified = 'inputdata/share/meshes/mpas/unified'
    under_unified = [name for name in staged if name.startswith(f'{unified}/')]
    assert under_unified, 'nothing was staged in the shared mesh directory'
    for name in under_unified:
        relative = name[len(unified) + 1 :]
        assert relative.startswith(f'{MESH_ID}/'), (
            f'{relative} is not under the {MESH_ID} subdirectory'
        )


def test_the_land_mesh_is_staged_for_every_target(tmp_path):
    """
    It comes from the cull step and describes a domain of the unified mesh, so
    a sea-ice-only task stages it too, exactly as it stages the SCRIP files.
    """
    mesh_dir = f'inputdata/share/meshes/mpas/unified/{MESH_ID}'
    for target, model in CASES:
        staged = _run_assemble(tmp_path / f'{target}_{model}', target, model)
        assert f'{mesh_dir}/{SHORT_NAME}.land.{CREATION_DATE}.nc' in staged


def test_no_mesh_is_staged_for_the_no_cavities_domain():
    """
    It exists to build mapping files, and under calving_front it is identical
    to the ocean mesh, so staging it would be a second copy of the same file.
    Its SCRIP description is still staged.
    """
    assert 'ocean_no_cavities' in names.SCRIP_REGIONS
    assert 'ocean_no_cavities' not in names.MESH_REGIONS
    with pytest.raises(ValueError, match='ocean_no_cavities'):
        names.culled_mesh_path(SHORT_NAME, CREATION_DATE, 'ocean_no_cavities')


@pytest.mark.parametrize(
    ('model', 'model_dir'), [('mpas-ocean', 'mpas-o'), ('omega', 'omega')]
)
def test_the_ocean_scrip_files_are_staged_in_both_places(
    tmp_path, model, model_dir
):
    """
    Developers look for them beside the ocean products as well as with the
    mesh files they were built from.  Both names point at the same file.
    """
    staged = _run_assemble(tmp_path, 'all', model)
    root = _assembly_dir(tmp_path, 'all', model) / ASSEMBLED_FILES

    mesh_dir = f'inputdata/share/meshes/mpas/unified/{MESH_ID}'
    ocn = f'inputdata/ocn/{model_dir}/{OCEAN_GRID}'
    pairs = [
        (
            f'{mesh_dir}/{SHORT_NAME}.ocean.scrip.{CREATION_DATE}.nc',
            f'{ocn}/{SHORT_NAME}.scrip.{CREATION_DATE}.nc',
        ),
        (
            f'{mesh_dir}/{SHORT_NAME}.ocean_no_cavities.scrip.'
            f'{CREATION_DATE}.nc',
            f'{ocn}/{SHORT_NAME}.no_cavities.scrip.{CREATION_DATE}.nc',
        ),
    ]
    for shared, beside_ocean in pairs:
        assert shared in staged
        assert beside_ocean in staged
        assert os.path.realpath(root / shared) == os.path.realpath(
            root / beside_ocean
        )


def test_the_land_scrip_has_no_copy_in_the_ocean_directory(tmp_path):
    """
    It has no business in an ocean directory, and dropping the region from the
    name would make it indistinguishable from the ocean one.
    """
    staged = _run_assemble(tmp_path, 'all')

    ocn = f'inputdata/ocn/mpas-o/{OCEAN_GRID}'
    assert not [
        name
        for name in staged
        if name.startswith(ocn) and 'land' in os.path.basename(name)
    ]


def test_no_sea_ice_mesh_is_staged(tmp_path):
    """
    The sea-ice mesh is the culled ocean mesh under another name, so staging
    it would put a second copy of the ocean mesh in the tree.  MPAS-Seaice
    reads its mesh from the initial condition, and the step still exists
    because the partition steps read its output.
    """
    _reset_shared_components()
    steps, _ = get_component_inputs_steps(mesh_name=MESH_NAME, target='seaice')
    assert 'seaice_mesh' in steps
    assert 'seaice_mesh' not in target_products('seaice', None)

    staged = _run_assemble(tmp_path, 'all')
    ice = f'inputdata/ice/mpas-seaice/{OCEAN_GRID}'
    assert f'{ice}/{SHORT_NAME}.{CREATION_DATE}.nc' not in staged
    assert f'{ice}/mpassi.{OCEAN_GRID}.{CREATION_DATE}.nc' in staged

    # and nothing anywhere else claims to be a sea-ice mesh
    assert not [name for name in staged if '.seaice.' in name]


def test_the_sync_script_is_available_but_not_staged(tmp_path):
    """
    Copying into a shared inputdata directory is a decision a person makes, so
    the step provides the script and never runs it -- and it does not belong
    in the staged tree either, since it is not an E3SM input.
    """
    _reset_shared_components()
    steps, _ = get_component_inputs_steps(
        mesh_name=MESH_NAME, model='mpas-ocean'
    )

    declared = [
        entry['filename'] for entry in steps['assemble_all'].input_data
    ]
    assert SYNC_SCRIPT in declared

    staged = _run_assemble(tmp_path, 'all')
    assert SYNC_SCRIPT not in staged


@pytest.mark.parametrize(
    'short_name, mesh_dir, ocean_dir',
    [
        ('u04-oi6to18-lr12p5', 'u04', 'u04-oi6to18'),
        ('uXX-oi-so12to30-lr10', 'uXX', 'uXX-oi-so12to30'),
        # an override for an ocean-only mesh has no land part to drop
        ('u99-oi30', 'u99', 'u99-oi30'),
    ],
)
def test_directories_follow_e3sm_grid_names(short_name, mesh_dir, ocean_dir):
    """
    E3SM names the ocean and sea-ice grid of a unified mesh for its ID and
    ocean half (u04-oi6to18), and the shared mesh directory for the ID alone.
    """
    date = CREATION_DATE
    grid = names.ocean_grid_name(short_name)
    assert grid == ocean_dir
    assert names.base_mesh_path(short_name, date) == (
        f'inputdata/share/meshes/mpas/unified/{mesh_dir}/'
        f'{short_name}.base.{date}.nc'
    )
    assert inputdata.ocean_initial_condition_path(grid, date) == (
        f'inputdata/ocn/mpas-o/{ocean_dir}/mpaso.{ocean_dir}.{date}.nc'
    )
    assert inputdata.omega_initial_condition_path(grid, date) == (
        f'inputdata/ocn/omega/{ocean_dir}/omega.{ocean_dir}.{date}.nc'
    )
    assert inputdata.seaice_initial_condition_path(grid, date) == (
        f'inputdata/ice/mpas-seaice/{ocean_dir}/mpassi.{ocean_dir}.{date}.nc'
    )
