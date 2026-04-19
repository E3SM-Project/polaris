import pathlib
import shutil
import zipfile


def extract_zip_member(zip_filename, member_name, out_filename):
    with zipfile.ZipFile(zip_filename) as archive:
        member_name = find_zip_member(archive, member_name)
        with archive.open(member_name) as src, open(out_filename, 'wb') as dst:
            shutil.copyfileobj(src, dst)


def find_zip_member(archive, member_name):
    names = archive.namelist()
    if member_name in names:
        return member_name

    basename = pathlib.Path(member_name).name
    matches = [name for name in names if pathlib.Path(name).name == basename]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError(
            f'Multiple ZIP members match {member_name!r}: {matches}'
        )
    raise ValueError(
        f'Could not find ZIP member {member_name!r} in archive '
        f'{archive.filename!r}'
    )
