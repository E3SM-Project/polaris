(dev-remapping)=

# Remapping

It is frequently useful when working with observational datasets or
visualizing MPAS data to remap between different global or regional grids and
meshes.  The [pyremap](https://mpas-dev.github.io/pyremap/stable/) provides
capabilities for making mapping files (which contain the weights needed to
interpolate between meshes) and using them to remap files or
{py:class}`xarray.Dataset` objects.  Polaris provides a step for producing
such a mapping file.  Under the hood, `pyremap` uses the
[ESMF_RegridWeightGen](https://earthsystemmodeling.org/docs/release/latest/ESMF_refdoc/node3.html#SECTION03020000000000000000)
or [mbtempest](https://sigma.mcs.anl.gov/moab/offline-remapping-workflow-with-mbtempest/)
tools, which use MPI parallelism.  To better support task parallelism, it is
best to have each MPI task be a separate polaris step.  For this reason, we
provide {py:class}`polaris.remap.MappingFileStep` to perform remapping.

A remapping step can be added to a task either by creating a
{py:class}`polaris.remap.MappingFileStep` object directly or by creating a
step that descends from the class.  Here is an example of using
`MappingFileStep` directly to remap data from a WOA 2023 lon-lat grid to an
MPAS mesh. This could happen in the task's `__init__()` or `configure()`
method:

```python

from polaris import Task
from polaris.config import PolarisConfigParser
from polaris.remap import MappingFileStep

class MyTestCase(Task):
    def __int__(self, component):
        step = MappingFileStep(component=component, name='make_map', ntasks=64,
                               min_tasks=1, method='bilinear')
        # add required config options related to mapping
        config = PolarisConfigParser(filepath=filepath)
        config.add_from_package('polaris.remap', 'mapping.cfg')
        step.set_shared_config(config, link='my_test_case.cfg')

        # indicate the the mesh from another step is an input to this step
        # note: the target is relative to the step, not the task.
        step.add_input_file(filename='woa.nc',
                            target='woa23_decav_0.25_extrap.20230414.nc',
                            database='initial_condition_database')

        step.add_input_file(filename='mesh.nc',
                            target='../mesh/mesh.nc')

        # you need to specify what type of source and destination mesh you
        # will use
        step.src_from_lon_lat(filename='woa.nc', lon_var='lon', lat_var='lat')
        step.dst_from_mpas(filename='mesh.nc', mesh_name='QU60')
```

Here is an example of creating a subclass to remap from an MPAS mesh to a
global lon-lat grid with a given resolution.  This is more convenient when you
want to use config options to allow users to customize the step.  Note that
you have to set a source and destination grid before calling
{py:meth}`polaris.remap.MappingFileStep.runtime_setup()`.  In the example, the
resolution of the lon-lat grid and the remapping method will be set using the
config options provided while setting up the polaris task.  We call the
`src_*()` and `dst_*()` methods in the `runtime_setup()` method to make sure
we pick up any changes to the config options that a user might have made
before running the task:

```python

from polaris.remap import MappingFileStep


class VizMap(MappingFileStep):
    def __init__(self, component, name, subdir, mesh_name, config):
        super().__init__(component=component, name=name, subdir=subdir,
                         ntasks=128, min_tasks=1)
        self.mesh_name = mesh_name
        self.add_input_file(filename='mesh.nc', target='../mesh/mesh.nc')

    def runtime_setup(self):
        config = self.config
        section = config['cosine_bell_viz']
        dlon = section.getfloat('dlon')
        dlat = section.getfloat('dlat')
        method = section.get('remap_method')
        self.src_from_mpas(filename='mesh.nc', mesh_name=self.mesh_name)
        self.dst_global_lon_lat(dlon=dlon, dlat=dlat, lon_min=0.)
        self.method = method

        super().runtime_setup()
```

It is important that the task that the step belongs to includes the required
config options related to mapping.  This could be accomplished either by
calling:
```python
config.add_from_package('polaris.remap', 'mapping.cfg')
```
or by including the corresponding config options in the task's config file:
```cfg
# config options related to creating mapping files
[mapping]

# The tool to use for creating mapping files: esmf or moab
map_tool = moab
```

Whether you create a `MappingFileStep` object directly or create a subclass,
you will need to call one of the `src_*()` methods to set up the source mesh or
grid and one of the `dst_*()` to configure the destination.  Expect for lon-lat
grids, you will need to provide a name for the mesh or grid, typically
describing its resolution and perhaps its extent and the region covered.

In nearly all situations, creating the mapping file is only one step in the
workflow. After that, the mapping file will be used to remap data between
the meshes or grids.  Steps that want to do this remapping need to have
the `MappingFileStep` (or its subclass) as a dependency (see
{ref}`dev-step-dependencies`).
