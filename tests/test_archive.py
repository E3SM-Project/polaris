import importlib.util
import zipfile
from pathlib import Path

import pytest


def _load_archive_module():
    module_path = (
        Path(__file__).resolve().parents[1] / 'polaris' / 'archive.py'
    )
    spec = importlib.util.spec_from_file_location(
        'polaris_archive', module_path
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_extract_zip_member_matches_member_by_basename(tmp_path):
    archive_module = _load_archive_module()
    zip_path = tmp_path / 'gebco_2023.zip'
    out_path = tmp_path / 'GEBCO_2023.nc'

    with zipfile.ZipFile(zip_path, 'w') as archive:
        archive.writestr('docs/readme.txt', 'GEBCO docs')
        archive.writestr('data/GEBCO_2023.nc', b'gebco-data')

    archive_module.extract_zip_member(
        str(zip_path), 'GEBCO_2023.nc', str(out_path)
    )

    assert out_path.read_bytes() == b'gebco-data'


def test_find_zip_member_raises_on_ambiguous_basename(tmp_path):
    archive_module = _load_archive_module()
    zip_path = tmp_path / 'gebco_2023.zip'

    with zipfile.ZipFile(zip_path, 'w') as archive:
        archive.writestr('a/GEBCO_2023.nc', b'a')
        archive.writestr('b/GEBCO_2023.nc', b'b')

    with zipfile.ZipFile(zip_path) as archive:
        with pytest.raises(ValueError, match='Multiple ZIP members'):
            archive_module.find_zip_member(archive, 'GEBCO_2023.nc')


def test_extract_zip_subdir_extracts_matching_members(tmp_path):
    archive_module = _load_archive_module()
    zip_path = tmp_path / 'HydroRIVERS_v10_shp.zip'

    with zipfile.ZipFile(zip_path, 'w') as archive:
        archive.writestr('HydroRIVERS_TechDoc_v10.pdf', b'pdf')
        archive.writestr('HydroRIVERS_v10_shp/HydroRIVERS_v10.shp', b'shp')
        archive.writestr('HydroRIVERS_v10_shp/HydroRIVERS_v10.dbf', b'dbf')

    archive_module.extract_zip_subdir(
        str(zip_path), 'HydroRIVERS_v10_shp', out_dir=str(tmp_path)
    )

    shp_dir = tmp_path / 'HydroRIVERS_v10_shp'
    assert (shp_dir / 'HydroRIVERS_v10.shp').read_bytes() == b'shp'
    assert (shp_dir / 'HydroRIVERS_v10.dbf').read_bytes() == b'dbf'
    assert not (tmp_path / 'HydroRIVERS_TechDoc_v10.pdf').exists()
