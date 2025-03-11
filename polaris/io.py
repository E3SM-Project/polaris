import grp
import os
import stat
import tempfile
from urllib.parse import urlparse

import progressbar
import requests


def download(url, dest_path, config, exceptions=True):  # noqa: C901
    """
    Download a file from a URL to the given path or path name

    Parameters
    ----------
    url : str
        The URL (including file name) to download

    dest_path : str
        The path (including file name) where the downloaded file should be
        saved

    config : polaris.config.PolarisConfigParser
        Configuration options used to find custom paths if ``dest_path`` is
        a config option

    exceptions : bool, optional
        Whether to raise exceptions when the download fails

    Returns
    -------
    dest_path : str
        The resulting file name if the download was successful, or None if not
    """

    in_file_name = os.path.basename(urlparse(url).path)
    dest_path = os.path.abspath(dest_path)
    out_file_name = os.path.basename(dest_path)

    do_download = config.getboolean('download', 'download')
    check_size = config.getboolean('download', 'check_size')
    verify = config.getboolean('download', 'verify')

    if not do_download:
        if not os.path.exists(dest_path):
            raise OSError(f'File not found and downloading is disabled: '
                          f'{dest_path}')
        return dest_path

    if not check_size and os.path.exists(dest_path):
        return dest_path

    session = requests.Session()
    if not verify:
        session.verify = False

    # dest_path contains full path, so we need to make the relevant
    # subdirectories if they do not exist already
    directory = os.path.dirname(dest_path)
    try:
        os.makedirs(directory)
    except OSError:
        pass

    try:
        response = session.get(url, stream=True)
        total_size = response.headers.get('content-length')
    except requests.exceptions.RequestException:
        if exceptions:
            raise
        else:
            print(f'  {url} could not be reached!')
            return None

    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        if exceptions:
            raise
        else:
            print(f'ERROR while downloading {in_file_name}:')
            print(e)
            return None

    if total_size is None:
        # no content length header
        if not os.path.exists(dest_path):
            dest_dir = os.path.dirname(dest_path)
            with open(dest_path, 'wb') as f:
                print(f'Downloading {in_file_name}\n'
                      f'  to {dest_dir}...')
                try:
                    f.write(response.content)
                except requests.exceptions.RequestException:
                    if exceptions:
                        raise
                    else:
                        print(f'  {in_file_name} failed!')
                        return None
                else:
                    print('  {in_file_name} done.')
    else:
        # we can do the download in chunks and use a progress bar, yay!

        total_size_int = int(total_size)
        if os.path.exists(dest_path) and \
                total_size_int == os.path.getsize(dest_path):
            # we already have the file, so just return
            return dest_path

        if out_file_name == in_file_name:
            file_names = in_file_name
        else:
            file_names = f'{in_file_name} as {out_file_name}'
        dest_dir = os.path.dirname(dest_path)
        print(f'Downloading {file_names} ({_sizeof_fmt(total_size_int)})\n'
              f'  to {dest_dir}')
        widgets = [progressbar.Percentage(), ' ', progressbar.Bar(),
                   ' ', progressbar.ETA()]
        bar = progressbar.ProgressBar(widgets=widgets,
                                      max_value=total_size_int).start()
        size = 0
        with open(dest_path, 'wb') as f:
            try:
                for data in response.iter_content(chunk_size=4096):
                    size += len(data)
                    f.write(data)
                    bar.update(size)
                bar.finish()
            except requests.exceptions.RequestException:
                if exceptions:
                    raise
                else:
                    print(f'  {in_file_name} failed!')
                    return None
            else:
                print(f'  {in_file_name} done.')
    return dest_path


def symlink(target, link_name, overwrite=True):
    """
    From https://stackoverflow.com/a/55742015/7728169
    Create a symbolic link named link_name pointing to target.
    If link_name exists then FileExistsError is raised, unless overwrite=True.
    When trying to overwrite a directory, IsADirectoryError is raised.

    Parameters
    ----------
    target : str
        The file path to link to

    link_name : str
        The name of the new link

    overwrite : bool, optional
        Whether to replace an existing link if one already exists
    """

    # make the directory that the link is in if it doesn't exist
    directory = os.path.dirname(os.path.abspath(link_name))
    try:
        os.makedirs(directory)
    except FileExistsError:
        pass

    if not overwrite:
        os.symlink(target, link_name)
        return

    # os.replace() may fail if files are on different filesystems
    link_dir = os.path.dirname(link_name)

    # Create link to target with temporary file_name
    while True:
        temp_link_name = tempfile.mktemp(dir=link_dir)

        # os.* functions mimic as closely as possible system functions
        # The POSIX symlink() returns EEXIST if link_name already exists
        # https://pubs.opengroup.org/onlinepubs/9699919799/functions/symlink.html
        try:
            os.symlink(target, temp_link_name)
            break
        except FileExistsError:
            pass

    # Replace link_name with temp_link_name
    try:
        # Preempt os.replace on a directory with a nicer message
        if not os.path.islink(link_name) and os.path.isdir(link_name):
            raise IsADirectoryError(
                f"Cannot symlink over existing directory: '{link_name}'")
        os.replace(temp_link_name, link_name)
    except Exception:
        if os.path.islink(temp_link_name):
            os.remove(temp_link_name)
        raise


def update_permissions(directories, group, show_progressbar=True):
    """
    Fix permissions on the databases where files were downloaded so
    everyone in the group can read/write to them

    Parameters
    ----------
    directories : list
        directories to change permissions on

    group : str
        The name of the group to set permissions to

    show_progressbar : bool, optional
        Whether to show a progress bar as permissions are updated
    """
    new_uid = os.getuid()
    new_gid = grp.getgrnam(group).gr_gid

    write_perm = (stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP |
                  stat.S_IWGRP | stat.S_IROTH)
    exec_perm = (stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR |
                 stat.S_IRGRP | stat.S_IWGRP | stat.S_IXGRP |
                 stat.S_IROTH | stat.S_IXOTH)

    mask = stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO

    if show_progressbar:
        print('changing permissions on downloaded files')

    # first the base directories that don't seem to be included in
    # os.walk()
    for directory in directories:
        root = None
        _set_dir_perms(root, directory, mask, exec_perm, new_uid, new_gid)

    files_and_dirs = _walk_dirs(directories)

    if show_progressbar:
        widgets = [progressbar.Percentage(), ' ', progressbar.Bar(),
                   ' ', progressbar.ETA()]
        bar = progressbar.ProgressBar(widgets=widgets,
                                      maxval=len(files_and_dirs)).start()
    else:
        bar = None
    progress = 0
    for base in directories:
        for root, dirs, files in os.walk(base):
            for directory in dirs:
                progress += 1
                if show_progressbar:
                    bar.update(progress)

                _set_dir_perms(root, directory, mask, exec_perm, new_uid,
                               new_gid)

            for file_name in files:
                progress += 1
                if show_progressbar:
                    bar.update(progress)
                file_name = os.path.join(root, file_name)
                _set_file_perms(root, file_name, mask, exec_perm, write_perm,
                                new_uid, new_gid)

    if show_progressbar:
        bar.finish()
        print('  done.')


def _walk_dirs(directories):
    """
    Walk through directories to find files to change
    """
    files_and_dirs = []
    for base in directories:
        for _, dirs, files in os.walk(base):
            files_and_dirs.extend(dirs)
            files_and_dirs.extend(files)
    return files_and_dirs


def _set_dir_perms(root, directory, mask, exec_perm, new_uid, new_gid):
    """
    Set permissions for a directory
    """
    if root is not None:
        directory = os.path.join(root, directory)

    try:
        dir_stat = os.stat(directory)
    except OSError:
        return

    if dir_stat.st_uid != new_uid:
        # current user doesn't own this dir so let's move on
        return

    perm = dir_stat.st_mode & mask

    if perm == exec_perm and dir_stat.st_gid == new_gid:
        return

    try:
        os.chown(directory, new_uid, new_gid)
        os.chmod(directory, exec_perm)
    except OSError:
        return


def _set_file_perms(root, file_name, mask, exec_perm, write_perm, new_uid,
                    new_gid):
    """
    Set permissions for a directory
    """
    file_name = os.path.join(root, file_name)
    try:
        file_stat = os.stat(file_name)
    except OSError:
        return

    if file_stat.st_uid != new_uid:
        # current user doesn't own this file so let's move on
        return

    perm = file_stat.st_mode & mask

    if perm & stat.S_IXUSR:
        # executable, so make sure others can execute it
        new_perm = exec_perm
    else:
        new_perm = write_perm

    if perm == new_perm and file_stat.st_gid == new_gid:
        return

    try:
        os.chown(file_name, new_uid, new_gid)
        os.chmod(file_name, new_perm)
    except OSError:
        return


# From https://stackoverflow.com/a/1094933/7728169
def _sizeof_fmt(num, suffix='B'):
    """
    Covert a number of bytes to a human-readable file size
    """
    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
        if abs(num) < 1024.0:
            return f"{num:3.1f}{unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}{'Yi'}{suffix}"
