(dev-io)=

# IO

A lot of I/O related tasks are handled internally in the step class
{py:class}`polaris.Step`.  Some of the lower level functions can be called
directly if need be.

(dev-io-symlink)=

## Symlinks

You can create your own symlinks that aren't input files (e.g. for a
README file that the user might want to have available) using
{py:func}`polaris.io.symlink()`:

```python
from importlib.resources import path

from polaris.io import symlink


def configure(task, config):
    ...
    with path('polaris.ocean.tasks.global_ocean.files_for_e3sm', 'README') as \
            target:
        symlink(str(target), '{}/README'.format(task['work_dir']))
```

In this example, we get the path to a README file within polaris and make
a local symlink to it in the task's work directory.  We did this with
`symlink()` rather than `add_input_file()` because we want this link to
be within the task's work directory, not the step's work directory.  We
must do this in `configure()` rather than `collect()` because we do not
know if the task will be set up at all (or in what work directory) during
`collect()`.

(dev-io-download)=

## Download

You can download files more directly if you need to using
{py:func}`polaris.io.download()`, though we recommend using
{py:meth}`polaris.Step.add_input_file()` whenever possible because it is more
flexible and takes care of more of the details of symlinking the local file
and adding it as an input to the step.  No current tasks use
`download()` directly, but an example might look like this:

```python
import os
from polaris.io import symlink, download

def setup(self):
    config = self.config
    step_dir = self.work_dir
    database_root = self.config.get('paths', 'database_root')
    download_path = os.path.join(database_root, 'mpas-ocean',
                                 'bathymetry_database')

    remote_filename = \
        'BedMachineAntarctica_and_GEBCO_2019_0.05_degree.200128.nc'
    local_filename = 'topography.nc'

    download(
        url=f'https://web.lcrc.anl.gov/public/e3sm/mpas_standalonedata/'
            f'mpas-ocean/bathymetry_database/{remote_filename}',
        config=config, dest_path=download_path)

    symlink(os.path.join(download_path, remote_filename),
            os.path.join(step_dir, local_filename))
```

In this example, the remote file
[BedMachineAntarctica_and_GEBCO_2019_0.05_degree.200128.nc](https://web.lcrc.anl.gov/public/e3sm/mpas_standalonedata/mpas-ocean/bathymetry_databaseBedMachineAntarctica_and_GEBCO_2019_0.05_degree.200128.nc)
gets downloaded into the bathymetry database (if it's not already there).
Then, we create a local symlink called `topography.nc` to the file in the
bathymetry database.

## Permissions

After downloading a file to a shared location, it is typically a good idea to
change permissions so others can access the file and write to the directory it
is stored in.

This can be accomplished with {py:func}`polaris.io.update_permissions()`,
which takes a list of one or more directories on which to update permissions,
along with a group name that files should belong to. As an example, if we
download a file `ocean.QU.240km.151209.nc` to a database `ocean/omega_ctest`,
we would then change permissions on the database so it is readable and writable
by the group identified by the `[e3sm_unified]/group` config option (if any) as
follows:
```python
import os
from polaris.io import download, update_permissions


machine = os.environ['POLARIS_MACHINE']

config = PolarisConfigParser()
config.add_from_package('polaris', 'default.cfg')
config.add_from_package('mache.machines', f'{machine}.cfg')
config.add_from_package('polaris.machines', f'{machine}.cfg')

database_root = config.get('paths', 'database_root')

base_url = 'https://web.lcrc.anl.gov/public/e3sm/polaris/'

filename = 'ocean.QU.240km.151209.nc'

database_path = 'ocean/omega_ctest'

download_path = os.path.join(database_root, database_path, filename)
url = f'{base_url}/{database_path}/{filename}'
download_target = download(url, download_path, config)

if config.has_option('e3sm_unified', 'group'):
    full_path = os.path.join(database_root, database_path)
    group = config.get('e3sm_unified', 'group')
    update_permissions([full_path], group)
```
This counts on us having set the `$POLARIS_MACHINE` environment variable, which
would be the case if the user has sourced a polaris load script.
