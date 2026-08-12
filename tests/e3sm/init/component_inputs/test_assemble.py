import logging
import os

import pytest
from geometric_features.aggregation import get_aggregator_by_name

from polaris.tasks.e3sm.init import e3sm_init
from polaris.tasks.e3sm.init.component_inputs.assemble import (
    SHARED_PRODUCTS,
    TARGET_PRODUCTS,
)
from polaris.tasks.e3sm.init.component_inputs.names import ASSEMBLED_FILES
from polaris.tasks.e3sm.init.component_inputs.steps import (
    get_component_inputs_steps,
)
from polaris.tasks.e3sm.init.component_inputs.tasks import (
    add_component_inputs_tasks,
)
from polaris.tasks.mesh import mesh as mesh_component
from polaris.tasks.mesh.spherical.feature_masks.moc import MOC_MASK_GROUP
from polaris.tasks.ocean import ocean

MESH_NAME = 'u.oi30.lr10'
SHORT_NAME = 'u02.oi30.lr10'
CREATION_DATE = '20250101'

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
    steps, _ = get_component_inputs_steps(mesh_name=MESH_NAME, target='ocean')

    assert [
        name for name, step in steps.items() if step.path.startswith('ocean/')
    ]
    assert 'simulation' in steps


@pytest.mark.parametrize('target', ['ocean', 'seaice', 'all'])
def test_each_target_stages_its_own_products(target):
    _reset_shared_components()
    steps, _ = get_component_inputs_steps(mesh_name=MESH_NAME, target=target)
    assemble = steps[f'assemble_{target}']

    expected = set(SHARED_PRODUCTS) | set(TARGET_PRODUCTS[target])
    assert set(assemble.product_steps) == expected


def test_an_unknown_target_is_rejected():
    _reset_shared_components()
    with pytest.raises(ValueError, match='land'):
        get_component_inputs_steps(mesh_name=MESH_NAME, target='land')


def test_the_tasks_live_under_a_directory_of_their_own():
    """
    Three tasks share most of their steps, so a task subdirectory could
    otherwise collide with a step subdirectory of the same name.
    """
    _reset_shared_components()
    add_component_inputs_tasks(component=e3sm_init)

    for target in TARGET_PRODUCTS:
        subdir = f'{MESH_NAME}/component_inputs/tasks/{target}'
        assert subdir in e3sm_init.tasks
        # no step lives under tasks/
        assert not [s for s in e3sm_init.steps if s.startswith(f'{subdir}/')]


def test_the_creation_date_is_fixed_at_setup():
    """
    Filled in during configure so it lands in the work directory's config; a
    re-run then keeps the date it was set up with rather than renaming every
    staged file to today's.
    """
    _reset_shared_components()
    add_component_inputs_tasks(component=e3sm_init)
    task = e3sm_init.tasks[f'{MESH_NAME}/component_inputs/tasks/all']

    assert task.config.get('component_inputs', 'creation_date').strip() == ''
    task.configure()
    first = task.config.get('component_inputs', 'creation_date')
    assert first != ''
    task.configure()
    assert task.config.get('component_inputs', 'creation_date') == first


@pytest.mark.parametrize('target', ['ocean', 'seaice', 'all'])
def test_every_product_lands_at_its_e3sm_path(tmp_path, target):
    """
    The D5 table, checked by running the step and listing what it built.
    """
    staged = _run_assemble(tmp_path, target)

    mesh_dir = 'inputdata/share/meshes/mpas/unified'
    expected = {
        'README',
        f'{mesh_dir}/{SHORT_NAME}.base.{CREATION_DATE}.nc',
        f'{mesh_dir}/{SHORT_NAME}.ocean.scrip.{CREATION_DATE}.nc',
        f'{mesh_dir}/{SHORT_NAME}.ocean_no_cavities.scrip.{CREATION_DATE}.nc',
        f'{mesh_dir}/{SHORT_NAME}.land.scrip.{CREATION_DATE}.nc',
    }
    if 'ocean_mesh' in TARGET_PRODUCTS[target]:
        ocn = f'inputdata/ocn/mpas-o/{SHORT_NAME}'
        expected |= {
            f'{ocn}/{SHORT_NAME}.{CREATION_DATE}.nc',
            f'{ocn}/mpaso.{SHORT_NAME}.{CREATION_DATE}.nc',
            f'{ocn}/{SHORT_NAME}.mocBasinsAndTransects'
            f'{FEATURES_DATE}.{CREATION_DATE}.nc',
        } | {
            f'{ocn}/partitions/mpas-o.graph.info.{CREATION_DATE}.part.{n}'
            for n in NCORES
        }
    if 'seaice_mesh' in TARGET_PRODUCTS[target]:
        ice = f'inputdata/ice/mpas-seaice/{SHORT_NAME}'
        expected |= {
            f'{ice}/{SHORT_NAME}.{CREATION_DATE}.nc',
            f'{ice}/mpassi.{SHORT_NAME}.{CREATION_DATE}.nc',
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
    root = tmp_path / 'assemble' / 'all' / ASSEMBLED_FILES

    mesh = (
        root
        / 'inputdata/ocn/mpas-o'
        / SHORT_NAME
        / f'mpaso.{SHORT_NAME}.{CREATION_DATE}.nc'
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
        _run_assemble(tmp_path, 'ocean', partitions=[])


def _run_assemble(
    tmp_path, target, partitions=None, creation_date=CREATION_DATE
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
        mesh_name=MESH_NAME, target=target
    )
    step = steps[f'assemble_{target}']

    config.set('component_inputs', 'creation_date', creation_date)
    step.config = config
    step.logger = LOGGER
    step.work_dir = str(tmp_path / 'assemble' / target)
    os.makedirs(step.work_dir, exist_ok=True)

    # the declared inputs, as the step will look for them
    for entry in step.input_data:
        path = os.path.join(step.work_dir, entry['filename'])
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
