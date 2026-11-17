import pytest

from polaris.config import PolarisConfigParser
from polaris.ocean.ice_shelf import IceShelfTask
from polaris.tasks.ocean import Ocean

FANSSIE_NAMELIST = """&land_ice
    config_use_land_ice_pressure = .false.
    config_land_ice_flux_mode = 'off'
/
"""

E3SM_PROJECT_NAMELIST = """&land_ice_fluxes
    config_land_ice_flux_mode = 'pressure_only'
/
"""


def test_configure_accepts_mpas_ocean_with_land_ice_pressure(tmp_path):
    task = _make_task(tmp_path, model='mpas-ocean', namelist=FANSSIE_NAMELIST)
    task.configure()


def test_configure_refuses_mpas_ocean_without_land_ice_pressure(tmp_path):
    task = _make_task(
        tmp_path, model='mpas-ocean', namelist=E3SM_PROJECT_NAMELIST
    )
    with pytest.raises(ValueError) as excinfo:
        task.configure()
    message = str(excinfo.value)
    assert 'config_use_land_ice_pressure' in message
    assert '--branch e3sm_submodules/FAnSSIE' in message


def test_configure_skips_a_missing_namelist(tmp_path):
    task = _make_task(tmp_path, model='mpas-ocean', namelist=None)
    task.configure()


def test_configure_skips_omega(tmp_path):
    task = _make_task(tmp_path, model='omega', namelist=E3SM_PROJECT_NAMELIST)
    task.configure()


def _make_task(tmp_path, model, namelist):
    """Make an ice-shelf task whose MPAS-Ocean build is in tmp_path"""
    component_path = tmp_path / 'ocean_build'
    namelist_filename = (
        component_path / 'default_inputs' / 'namelist.ocean.forward'
    )
    if namelist is not None:
        namelist_filename.parent.mkdir(parents=True)
        namelist_filename.write_text(namelist)

    config = PolarisConfigParser()
    config.set('ocean', 'model', model)
    config.set('paths', 'component_path', str(component_path))
    config.set('namelists', 'forward', str(namelist_filename))

    task = IceShelfTask(
        component=Ocean(),
        min_resolution=5.0,
        name='default',
        subdir='planar/ice_shelf_test/default',
    )
    task.config = config
    return task
