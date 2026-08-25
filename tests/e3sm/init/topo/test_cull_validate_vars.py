import os

from polaris.component import Component
from polaris.mesh.reconstruct import get_reconstruction_validate_vars
from polaris.mesh.validate import MPAS_MESH_VALIDATE_VARS
from polaris.tasks.e3sm.init import e3sm_init
from polaris.tasks.e3sm.init.topo.cull.tasks import add_cull_topo_tasks
from polaris.tasks.mesh import mesh as mesh_component

UNIFIED_MESH_NAME = 'u.oi30.lr10'
SIMPLE_MESH_NAME = 'qu240km'

# The output files each step of the cull task compares against a baseline.
# Steps without NetCDF outputs (e.g. the GeoJSON-only river-simplify step)
# are absent, as are outputs that are re-encodings of files that are already
# validated (SCRIP files and graph files).
UNIFIED_VALIDATED_FILES = {
    'combine_topo_bedmap3_gebco2023_lat_lon_0.03125_degree': [
        'bedmap3_gebco2023_0.03125_degree.nc',
    ],
    'coastline_compute': [
        'coastline_bedrock_zero.nc',
        'coastline_calving_front.nc',
        'coastline_grounding_line.nc',
    ],
    'coastline_remap': [
        'coastline_bedrock_zero.nc',
        'coastline_calving_front.nc',
        'coastline_grounding_line.nc',
    ],
    'river_rasterize': ['river_network.nc'],
    'river_clip': ['clipped_river_network.nc'],
    'sizing_field': ['sizing_field.nc'],
    'base_mesh': ['base_mesh.nc', 'cellWidthVsLatLon.nc'],
    'combine_topo_bedmap3_gebco2023_cubed_sphere_ne3000': [
        'bedmap3_gebco2023_ne3000.nc',
    ],
    'mask_topo': ['topography_masked.nc'],
    'remap_unsmoothed': ['topography_remapped.nc'],
    'remap_smoothed': ['topography_remapped.nc'],
    'cull_mask': ['cull_masks.nc'],
    'cull_mesh': [
        'culled_land_mesh.nc',
        'culled_ocean_mesh.nc',
        'culled_ocean_no_cavities_mesh.nc',
        'culled_ocean_no_cavities_reconstruction_weights.nc',
        'culled_ocean_reconstruction_weights.nc',
        'land_map_culled_to_base.nc',
        'ocean_map_culled_to_base.nc',
        'ocean_no_cavities_map_culled_to_base.nc',
    ],
}


def test_unified_cull_task_steps_validate_netcdf_outputs(tmp_path):
    steps = _setup_cull_task_steps(UNIFIED_MESH_NAME, tmp_path)

    validated = {
        name: sorted(step.validate_vars)
        for name, step in steps.items()
        if step.validate_vars
    }
    expected = {
        name: sorted(filenames)
        for name, filenames in UNIFIED_VALIDATED_FILES.items()
    }
    assert validated == expected


def test_simple_base_mesh_validates_reconstruction_weights(tmp_path):
    steps = _setup_cull_task_steps(SIMPLE_MESH_NAME, tmp_path)

    base_mesh_step = steps['qu_base_mesh_240km']
    assert (
        base_mesh_step.validate_vars['base_mesh.nc'] == MPAS_MESH_VALIDATE_VARS
    )
    assert base_mesh_step.validate_vars['cellWidthVsLatLon.nc'] == [
        'cellWidth'
    ]
    assert base_mesh_step.validate_vars[
        'reconstruction_weights.nc'
    ] == get_reconstruction_validate_vars(location='cell')


def test_unified_base_mesh_skips_reconstruction_weights(tmp_path):
    # unified meshes get culled, so the base mesh doesn't compute weights
    steps = _setup_cull_task_steps(UNIFIED_MESH_NAME, tmp_path)

    base_mesh_step = steps['base_mesh']
    assert 'reconstruction_weights.nc' not in base_mesh_step.validate_vars


def test_culled_meshes_validate_the_full_mesh(tmp_path):
    steps = _setup_cull_task_steps(UNIFIED_MESH_NAME, tmp_path)

    validate_vars = steps['cull_mesh'].validate_vars
    for prefix in ['ocean', 'ocean_no_cavities', 'land']:
        assert (
            validate_vars[f'culled_{prefix}_mesh.nc']
            == MPAS_MESH_VALIDATE_VARS
        )
        assert validate_vars[f'{prefix}_map_culled_to_base.nc'] == [
            'mapCulledToBaseCell',
            'mapCulledToBaseEdge',
            'mapCulledToBaseVertex',
        ]


def test_sizing_field_validates_cull_emulation_fields(tmp_path):
    steps = _setup_cull_task_steps(UNIFIED_MESH_NAME, tmp_path)

    sizing_step = steps['sizing_field']
    assert sizing_step.config.getboolean(
        'sizing_field', 'enable_cull_emulation'
    )
    validate_vars = sizing_step.validate_vars['sizing_field.nc']
    assert 'cellWidth' in validate_vars
    for var in [
        'effective_ocean_mask',
        'emulated_ocean_mask',
        'mesh_scale_ocean_fraction',
        'passages_widened',
    ]:
        assert var in validate_vars


def test_remapped_topo_validates_fractions_and_masked_fields(tmp_path):
    steps = _setup_cull_task_steps(UNIFIED_MESH_NAME, tmp_path)

    validate_vars = steps['remap_unsmoothed'].validate_vars[
        'topography_remapped.nc'
    ]
    # masks have become fractions after remapping
    assert 'ocean_mask' not in validate_vars
    for var in [
        'base_elevation',
        'ocean_frac',
        'land_frac',
        'ocean_masked_base_elevation',
        'land_masked_ice_frac',
    ]:
        assert var in validate_vars


def test_topo_validate_vars_skip_the_combined_ocean_mask(tmp_path):
    # the cached combined topography files predate ocean_mask, so neither it
    # nor anything derived from it can be compared against a baseline
    steps = _setup_cull_task_steps(UNIFIED_MESH_NAME, tmp_path)

    combine_step = steps['combine_topo_bedmap3_gebco2023_cubed_sphere_ne3000']
    combined_vars = combine_step.validate_vars['bedmap3_gebco2023_ne3000.nc']
    assert 'ocean_mask' not in combined_vars

    masked_vars = steps['mask_topo'].validate_vars['topography_masked.nc']
    # the mask-topography step adds its own ocean mask, which is compared
    assert 'ocean_mask' in masked_vars
    for prefix in ['land', 'ocean']:
        assert f'{prefix}_masked_ocean_mask' not in masked_vars

    for name in ['remap_unsmoothed', 'remap_smoothed']:
        remapped_vars = steps[name].validate_vars['topography_remapped.nc']
        # the ocean mask that the mask-topography step adds becomes a
        # fraction that is compared
        assert 'ocean_frac' in remapped_vars
        for prefix in ['land', 'ocean']:
            assert f'{prefix}_masked_ocean_frac' not in remapped_vars


def _setup_cull_task_steps(mesh_name, work_dir):
    """
    Build the cull task for ``mesh_name`` and set up each of its steps in
    ``work_dir`` so that ``validate_vars`` added during setup are available
    """
    _reset_shared_components()

    component = Component(name='e3sm/init')
    add_cull_topo_tasks(component=component)
    task = component.tasks[f'{mesh_name}/topo/cull']
    for step in task.steps.values():
        step.base_work_dir = str(work_dir)
        step.work_dir = os.path.join(str(work_dir), step.subdir)
        step.setup()
    return task.steps


def _reset_shared_components():
    for component in [e3sm_init, mesh_component]:
        component.tasks.clear()
        component.steps.clear()
        component.configs.clear()
