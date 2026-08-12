import numpy as np
import pytest
import xarray as xr
from geometric_features.aggregation import get_aggregator_by_name

from polaris.tasks.e3sm.init import e3sm_init
from polaris.tasks.e3sm.init.component_inputs import names
from polaris.tasks.e3sm.init.component_inputs.assemble import TARGET_PRODUCTS
from polaris.tasks.e3sm.init.component_inputs.moc_masks import (
    MESH_FILENAME,
)
from polaris.tasks.e3sm.init.component_inputs.steps import (
    get_component_inputs_steps,
)
from polaris.tasks.mesh import mesh as mesh_component
from polaris.tasks.mesh.spherical.feature_masks.moc import (
    MOC_MASK_GROUP,
    moc_masks_filename,
)
from polaris.tasks.ocean import ocean

MESH_NAME = 'u.oi30.lr10'
SHORT_NAME = 'u02.oi30.lr10'
CREATION_DATE = '20250101'


def test_the_masks_are_built_from_the_culled_ocean_mesh():
    """
    The full ocean domain, matching what the ocean initial condition is built
    from, rather than the no-cavities mesh that exists for mapping files.

    The framework declares its inputs in ``setup()``, so this reads the
    configured filename and the upstream step rather than ``input_data``.
    """
    _reset_shared_components()
    steps, config = get_component_inputs_steps(mesh_name=MESH_NAME)

    step = steps['ocean_moc_masks']
    assert step.mesh_filename == MESH_FILENAME
    assert step.mesh_step is steps['cull_mesh']
    assert config.get('feature_masks', 'mesh_filename') == MESH_FILENAME


def test_the_masks_are_an_ocean_product():
    """
    The sea-ice target has no use for them, and asking for it must not build
    the step.
    """
    _reset_shared_components()
    steps, _ = get_component_inputs_steps(mesh_name=MESH_NAME, target='seaice')
    assert 'ocean_moc_masks' not in steps

    for target in ['ocean', 'all']:
        _reset_shared_components()
        steps, _ = get_component_inputs_steps(
            mesh_name=MESH_NAME, target=target
        )
        assert 'ocean_moc_masks' in steps
        assert 'ocean_moc_masks' in TARGET_PRODUCTS[target]


def test_the_step_needs_no_ocean_component():
    """
    What the first attempt got wrong.  Subclassing the ocean feature-mask step
    dragged in OceanIOStep, whose process_inputs_and_outputs reads
    ``[ocean] model``, and the component_inputs config has no ``[ocean]``
    section by design.  Setup failed with NoSectionError.
    """
    _reset_shared_components()
    steps, config = get_component_inputs_steps(mesh_name=MESH_NAME)

    step = steps['ocean_moc_masks']
    assert step.component is e3sm_init
    assert not config.has_section('ocean')

    ocean_io = [
        cls.__name__
        for cls in type(step).__mro__
        if cls.__name__ in ('OceanIOStep', 'ComputeOceanFeatureMasksStep')
    ]
    assert ocean_io == []


def test_the_moc_behavior_comes_from_the_shared_helpers():
    """
    Not from a copy of it here.  The ocean feature-mask step uses the same
    two helpers, so the filename convention and the southern-boundary
    transects cannot drift apart between the two callers.
    """
    _reset_shared_components()
    steps, _ = get_component_inputs_steps(mesh_name=MESH_NAME)

    step = steps['ocean_moc_masks']
    assert step.output_filename == moc_masks_filename(
        mesh_name=MESH_NAME, date=step.features_date
    )
    assert step.mask_group == MOC_MASK_GROUP


def test_the_step_knows_its_filename_before_setup():
    """
    The assembly step reads ``output_filename`` while it is being built, which
    is before ``setup()`` runs.  If the step only named its output in
    ``setup()``, assembly would declare nothing and stage nothing.
    """
    _reset_shared_components()
    steps, _ = get_component_inputs_steps(mesh_name=MESH_NAME)

    step = steps['ocean_moc_masks']
    assert step.output_filename is not None
    assert 'mocBasinsAndTransects' in step.output_filename

    declared = [
        entry['filename']
        for entry in steps['assemble_all'].input_data
        if entry['filename'].startswith('ocean_moc_masks__')
    ]
    assert declared == [f'ocean_moc_masks__{step.output_filename}']


def test_the_features_date_comes_from_the_aggregation():
    """
    Not from a literal in Polaris.  The date belongs to geometric_features,
    and the staged name has to follow it when it changes.
    """
    _reset_shared_components()
    steps, _ = get_component_inputs_steps(mesh_name=MESH_NAME)

    _, _, date = get_aggregator_by_name(MOC_MASK_GROUP)
    assert steps['ocean_moc_masks'].features_date == date


def test_the_staged_name_carries_both_dates():
    """
    The aggregation date rides with the product name; the creation date stays
    in the trailing field, as it does for every other staged file.
    """
    path = names.ocean_moc_masks_path(
        short_name=SHORT_NAME,
        creation_date=CREATION_DATE,
        features_date='20210623',
    )

    assert path == (
        f'inputdata/ocn/mpas-o/{SHORT_NAME}/'
        f'{SHORT_NAME}.mocBasinsAndTransects20210623.{CREATION_DATE}.nc'
    )
    # the last dotted field is the creation date here as on every other staged
    # file, so that rule survives this file having two dates
    assert path.endswith(f'.{CREATION_DATE}.nc')


def test_the_two_dates_move_independently():
    """
    Either date can change without the other, which is why the name carries
    both.
    """
    base = names.ocean_moc_masks_path(SHORT_NAME, '20250101', '20210623')
    newer_features = names.ocean_moc_masks_path(
        SHORT_NAME, '20250101', '20260101'
    )
    newer_creation = names.ocean_moc_masks_path(
        SHORT_NAME, '20260202', '20210623'
    )

    assert len({base, newer_features, newer_creation}) == 3


def test_the_mask_file_records_where_it_came_from(tmp_path):
    """
    Both dates are written as attributes as well, so the provenance survives a
    copy or a rename off the inputdata server.
    """
    _reset_shared_components()
    steps, config = get_component_inputs_steps(mesh_name=MESH_NAME)
    step = steps['ocean_moc_masks']

    config.set('component_inputs', 'creation_date', CREATION_DATE)
    step.config = config

    ds_masks = xr.Dataset({'regionCellMasks': ('nCells', np.zeros(4, int))})
    written = tmp_path / 'masks.nc'
    step._write_mask_dataset(ds_masks, str(written))

    with xr.open_dataset(written) as ds:
        assert ds.attrs['mask_features_date'] == step.features_date
        assert ds.attrs['creation_date'] == CREATION_DATE
        assert MOC_MASK_GROUP in ds.attrs['mask_features_source']


def test_omega_raises_before_any_masks_are_built():
    """
    D9: the gate belongs on every product step, not only the ones that write
    model files.
    """
    _reset_shared_components()
    steps, config = get_component_inputs_steps(mesh_name=MESH_NAME)
    step = steps['ocean_moc_masks']

    config.set('component_inputs', 'ocean_model', 'omega')
    step.config = config

    with pytest.raises(NotImplementedError, match='Omega'):
        step.run()


def _reset_shared_components():
    for component in [e3sm_init, mesh_component, ocean]:
        component.tasks.clear()
        component.steps.clear()
        component.configs.clear()
