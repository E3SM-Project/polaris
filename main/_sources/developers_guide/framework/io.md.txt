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


def configure(testcase, config):
    ...
    with path('polaris.ocean.tests.global_ocean.files_for_e3sm', 'README') as \
            target:
        symlink(str(target), '{}/README'.format(testcase['work_dir']))
```

In this example, we get the path to a README file within polaris and make
a local symlink to it in the test case's work directory.  We did this with
`symlink()` rather than `add_input_file()` because we want this link to
be within the test case's work directory, not the step's work directory.  We
must do this in `configure()` rather than `collect()` because we do not
know if the test case will be set up at all (or in what work directory) during
`collect()`.

(dev-io-download)=

## Download

You can download files more directly if you need to using
{py:func}`polaris.io.download()`, though we recommend using
{py:meth}`polaris.Step.add_input_file()` whenever possible because it is more
flexible and takes care of more of the details of symlinking the local file
and adding it as an input to the step.  No current test cases use
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

