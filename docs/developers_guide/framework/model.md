(dev-model)=

# Model

## Running an E3SM component

Steps that run a standalone build of an E3SM component should descend from the
{py:class}`polaris.ModelStep` class.

By default (if the attribute `update_pio = True`), at runtime, the namelist 
options associated with the [PIO library](https://ncar.github.io/ParallelIO/) 
will automatically be set.  If the `make_graph = True`, the mesh will be 
partitioned across MPI tasks at runtime.

During construction or by setting attributes directly, you can can provide 
non-default names for the graph, namelist and streams files.  At construction
or with the {py:meth}`polaris.ModelStep.set_model_resources()` 
method,  you can set number of tasks, threads, etc. determined from the 
`ntasks`, `min_tasks`, `cpus_per_task`, `` min_cpus_per_task` `` and 
`openmp_threads` attributes.  These resources need to be set at construction or
in the  {ref}`dev-step-setup` method (i.e. before calling {ref}`dev-step-run`) 
so that  the polaris framework  can ensure that the required resources are 
available.

(dev-model-yaml-namelists-and-streams)=

### Adding yaml, namelist and streams files

Components and tasks can provide yaml config options, 
namelist and streams files that are used to replace default model config 
options  and streams definitions before the E3SM component gets run.  Namelist 
and streams files within the `polaris` package must start with the prefix 
`namelist.` and `streams.`,  respectively, to ensure that they are included 
when we build the package.  Yaml files must end with `.yaml` or `.yml` for the
same reason.

You can make calls to {py:meth}`polaris.ModelStep.add_namelist_file()`,
{py:meth}`polaris.ModelStep.add_yaml_file()`,
{py:meth}`polaris.ModelStep.add_model_config_options()`  and
{py:meth}`polaris.ModelStep.add_streams_file()` as described below to indicate 
how yaml, namelist and streams file should be built up by modifying the 
defaults for the  E3SM component.  The yaml, namelists and streams files 
themselves  are generated  automatically (which of these depends on the E3SM
component in question) as part of setting up the task.

(dev-model-add-yaml-file)=

#### Adding a yaml file

Typically, a step that runs an E3SM component will include one or more calls 
to  {py:meth}`polaris.ModelStep.add_namelist_file()` or
{py:meth}`polaris.ModelStep.add_yaml_file()` within the {ref}`dev-step-init`
or {ref}`dev-step-setup` method.  Calling one of these methods simply adds the
file to  a list that will be parsed if and when the step gets set up.  (This 
way, it is  safe to add namelist files to a step in init even if that task
will never  get set up or run.)

The format of the yaml file is a hierarchical list of sections with config
options and values, followed by streams:

``` yaml
ocean:
  run_modes:
    config_ocean_run_mode: forward
  time_management:
    config_run_duration: 0024_00:00:00
  ALE_vertical_grid:
    config_vert_coord_movement: impermeable_interfaces
  decomposition:
    config_block_decomp_file_prefix: graph.info.part.
  time_integration:
    config_time_integrator: RK4
  
  streams:
    mesh:
      filename_template: init.nc
    input:
      filename_template: init.nc
    restart:
      output_interval: 0030_00:00:00
    output:
      type: output
      filename_template: output.nc
      output_interval: 0024_00:00:00
      clobber_mode: truncate
      reference_time: 0001-01-01_00:00:00
      contents:
      - tracers
      - mesh
      - xtime
      - normalVelocity
      - layerThickness
      - refZMid
      - refLayerThickness
      - kineticEnergyCell
      - relativeVorticityCell
```

Unlike for namelist files (see below), we require that config options be placed
in appropriate sections both for clarity and because there is no guarantee that
config options must have unique names.

A typical yaml file is added by passing a package where the yaml file
is located and the name of the input yaml file within that package
as arguments to {py:meth}`polaris.ModelStep.add_yaml_file()`:

```python
self.add_yaml_file('polaris.ocean.tasks.global_convergence.cosine_bell',
                   'forward.yaml')
```

Model config values are replaced by the files (or options, see below) in the
sequence they are given.  This way, you can add the model config substitutions
common to related tasks first, and then override those with the replacements 
specific to the task or step.

(dev-model-add-namelists-file)=

#### Adding a namelist file

Typically, a step that runs the E3SM component will include one or more calls 
to  {py:meth}`polaris.ModelStep.add_namelist_file()` or
{py:meth}`polaris.ModelStep.add_yaml_file()` within the {ref}`dev-step-init`
or {ref}`dev-step-setup` method.  Calling this method simply adds the file to
a list that will be parsed if and when the step gets set up.  (This way, it is
safe to add namelist files to a step in init even if that task will never
get set up or run.)

The format of the namelist file is simply a list of namelist options and
the replacement values:

```none
config_write_output_on_startup = .false.
config_run_duration = '0000_00:15:00'
config_use_mom_del2 = .true.
config_implicit_bottom_drag_coeff = 1.0e-2
config_use_cvmix_background = .true.
config_cvmix_background_diffusion = 0.0
config_cvmix_background_viscosity = 1.0e-4
```

Since all MPAS namelist options must have unique names, we do not worry about
which specific namelist within the file each belongs to.

A typical namelist file is added by passing a package where the namelist file
is located and the name of the input namelist file within that package
as arguments to {py:meth}`polaris.ModelStep.add_namelist_file()`:

```python
self.add_namelist_file('polaris.ocean.tasks.baroclinic_channel',
                       'namelist.forward')
```

Namelist values are replaced by the files (or options, see below) in the
sequence they are given.  This way, you can add the namelist substitutions for
that are common to related tasks first, and then override those with the 
replacements that are specific to the task or step.

(dev-model-add-model-config-options)=

#### Adding model config options

Sometimes, it is easier to replace yaml or namelist options (together referred
to as model config options)  using a dictionary within  the code, rather than 
a yaml or namelist file.  This is appropriate when there are only 1 or 2 
options to  replace (so creating a file seems like overkill) or when the
model config options rely on values that are determined by the code (e.g. 
different  values for different resolutions).  Simply create a dictionary
replacements and call {py:meth}`polaris.ModelStep.add_model_config_options()` 
either  at init or in the `setup()` method of the step.  These replacements are
parsed, along  with replacements from files, in the order they are added.  
Thus, you could add replacements from a model config file common to multiple
tasks, specific to a task, and/or specific to step.  Then, you could override 
them with namelist options in a dictionary for the task or step, as in this 
example:

```python
if nu is not None:
    # update the viscosity to the requested value
    self.add_model_config_options(options=dict(config_mom_del2=nu))

# make sure output is double precision
self.add_yaml_file('polaris.ocean.config', 'output.yaml')

self.add_yaml_file('polaris.ocean.tasks.baroclinic_channel',
                   'forward.yaml')

```

Here, we set the viscosity `nu`, which is an option passed in when creating 
this step.  Then, we get default model config options for ocean model output
(`output.yaml`) and for baroclinic channel forward steps (`forward.yaml`).

:::{note}
Model config options can have values of type `bool`, `int`, `float` or `str`,
and are automatically converted to the appropriate type in the yaml or namelist
file.
:::

(dev-model-dynamic-model-config-options)=

#### Dynamic model config options

It is sometimes useful to have model config options that are based on Polaris
config options and/or algorithms.  In such cases, the model config options
need to be computed once at setup and again (possibly based on updated
config options) at runtime.  A step needs to override the 
{py:meth}`polaris.ModelStep.dynamic_model_config()` method, e.g.:

```python
def dynamic_model_config(self, at_setup):
    """
    Add model config options, namelist, streams and yaml files using config
    options or template replacements that need to be set both during step
    setup and at runtime

    Parameters
    ----------
    at_setup : bool
        Whether this method is being run during setup of the step, as
        opposed to at runtime
    """
    super().dynamic_model_config(at_setup)

    config = self.config

    options = dict()

    # dt is proportional to resolution: default 30 seconds per km
    dt_per_km = config.getfloat('baroclinic_channel', 'dt_per_km')
    dt = dt_per_km * self.resolution
    # https://stackoverflow.com/a/1384565/7728169
    options['config_dt'] = \
        time.strftime('%H:%M:%S', time.gmtime(dt))

    if self.run_time_steps is not None:
        # default run duration is a few time steps
        run_seconds = self.run_time_steps * dt
        options['config_run_duration'] = \
            time.strftime('%H:%M:%S', time.gmtime(run_seconds))

    # btr_dt is also proportional to resolution: default 1.5 seconds per km
    btr_dt_per_km = config.getfloat('baroclinic_channel', 'btr_dt_per_km')
    btr_dt = btr_dt_per_km * self.resolution
    options['config_btr_dt'] = \
        time.strftime('%H:%M:%S', time.gmtime(btr_dt))

    self.dt = dt
    self.btr_dt = btr_dt

    self.add_model_config_options(options=options)
```

(dev-model-add-streams-file)=

#### Adding a streams file

Streams files are a bit more complicated than namelist files because
streams files are XML documents, requiring some slightly more sophisticated
parsing.

Typically, a step that runs the E3SM component will include one or more calls
to {py:meth}`polaris.ModelStep.add_streams_file()` within the  
{ref}`dev-step-init` or {ref}`dev-step-setup` method.  Calling this function 
simply adds the file to a list within the `step` dictionary that will be parsed
if an when the step gets set up.  (This way, it is safe to add streams files to
a step at init even if that task will never get set up or run.)

The format of the streams file is essentially the same as the default and
generated streams file, e.g.:

```xml
<streams>

<immutable_stream name="mesh"
                  filename_template="init.nc"/>

<immutable_stream name="input"
                  filename_template="init.nc"/>

<immutable_stream name="restart"/>

<stream name="output"
        type="output"
        filename_template="output.nc"
        output_interval="0000_00:00:01"
        clobber_mode="truncate">

    <var_struct name="tracers"/>
    <var name="xtime"/>
    <var name="normalVelocity"/>
    <var name="layerThickness"/>
</stream>

</streams>
```

These are all streams that are already defined in the default forward streams
for MPAS-Ocean, so the defaults will be updated.  If only the attributes of
a stream are given, the contents of the stream (the `var`, `var_struct`
and `var_array` tags within the stream) are taken from the defaults.  If
any contents are given, as for the `output` stream in the example above, they
replace the default contents.  Polaris does not include a way to add or
remove contents from the defaults, just keep the default contents or replace
them all.  (Past experience has shown that such a feature would be
confusing and difficult to keep synchronized with the E3SM code.)

A typical streams file is added by calling
{py:meth}`polaris.ModelStep.add_streams_file()` with a package where the streams
file is located and the name of the input streams file within that package:

```python
self.add_streams_file('polaris.ocean.tasks.baroclinic_channel',
                      'streams.forward')
```

If the streams file should have a different name than the default
(`streams.<component>`), the name can be given via the `out_name` keyword
argument.   If `init` mode is desired, rather than the default, `forward`
mode, this can also be specified.

(dev-model-add-streams-file-template)=

#### Adding a template streams file

The main difference between namelists and streams files is that there is no
direct equivalent for streams of {py:meth}`polaris.ModelStep.add_model_config_options()`.
It is simply too confusing to try to define streams within the code.

Instead, {py:meth}`polaris.ModelStep.add_streams_file()` includes a keyword
argument `template_replacements`.  If you provide a dictionary of
replacements to this argument, the input streams file will be treated as a
[Jinja2 template](https://jinja.palletsprojects.com/) that is rendered
using the provided replacements.  Here is an example of such a template streams
file:

```xml
<streams>

<stream name="output"
        output_interval="{{ output_interval }}"/>
<immutable_stream name="restart"
                  filename_template="../restarts/rst.$Y-$M-$D_$h.$m.$s.nc"
                  output_interval="{{ restart_interval }}"/>

</streams>
```

And here is how it would be added, along with replacements:

```python
stream_replacements = {
    'output_interval': '00-00-01_00:00:00',
    'restart_interval': '00-00-01_00:00:00'}
add_streams_file(step, module, 'streams.template',
                 template_replacements=stream_replacements)

...

stream_replacements = {
    'output_interval': '00-00-01_00:00:00',
    'restart_interval': '00-00-01_00:00:00'}
add_streams_file(step, module, 'streams.template',
                 template_replacements=stream_replacements)
```

In this example, taken from
{py:class}`polaris.ocean.tasks.global_ocean.mesh.qu240.dynamic_adjustement.QU240DynamicAdjustment`,
we are creating a series of steps that will be used to perform dynamic
adjustment of the ocean model, each of which might have different durations and
restart intervals.  Rather than creating a streams file for each step of the
spin up, we reuse the same template with just a few appropriate replacements.
Thus, calls to {py:meth}`polaris.ModelStep.add_streams_file()` with
`template_replacements` are qualitatively similar to namelist calls to
{py:meth}`polaris.ModelStep.add_model_config_options()`.

### Adding E3SM component as an input

If a step involves running the E3SM component, it should descend from 
:py:class`polaris.ModelStep`.  The model executable will  automatically be 
linked and added as an input to the step.  This way, if the user has forgotten
to compile the model, this will be obvious by the broken symlink and the step 
will immediately fail because of the missing input.  The path to the executable
is automatically detected based on the work directory for the step and the 
config options.

## Partitioning the mesh

The method {py:meth}`polaris.ModelStep.partition()` calls the graph 
partitioning  executable ([gpmetis](https://arc.vt.edu/userguide/metis/) by 
default) to  divide up the MPAS mesh across MPI tasks.  If you create a
`ModelStep` with `partition_graph=True` (the default), this method is called 
automatically.

In some circumstances, a step may need to partition the mesh separately from
running the model.  Typically, this applies to cases where the model is run
multiple times with the same partition and we don't want to waste time
creating the same partition over and over.  For such cases, you can
provide `partition_graph=False` and then call
{py:meth}`polaris.ModelStep.partition()` manually where appropriate.

## Updating PIO namelist options

You can use {py:meth}`polaris.ModelStep.update_namelist_pio()` to 
automatically set  the MPAS namelist options `config_pio_num_iotasks` and 
`config_pio_stride` such that there is 1 PIO task per node of the MPAS run.  
This is particularly useful for PIO v1, which we have found performs much 
better in this  configuration than when there is 1 PIO task per core, the MPAS 
default.  When running with PIO v2, we have found little performance difference
between the MPAS default and the polaris default of one task per node, so we 
feel this is a safe default.

By default, this function is called in 
{py:meth}`polaris.ModelStep.runtime_setup()`.  If the same namelist 
file is used for multiple model runs, it may be useful to update the number of 
PIO tasks only once.  In this case, set the attribute `update_pio = False` and
{py:meth}`polaris.ModelStep.update_namelist_pio()` yourself.

If you wish to use the MPAS default behavior of 1 PIO task per core, or wish to
set `config_pio_num_iotasks` and `config_pio_stride` yourself, simply
set `update_pio = False`.

## Making a graph file

Some polaris tasks take advantage of the fact that the
[MPAS-Tools cell culler](http://mpas-dev.github.io/MPAS-Tools/stable/mesh_conversion.html#cell-culler)
can produce a graph file as part of the process of culling cells from an
MPAS mesh.  In tasks that do not require cells to be culled, you can
call {py:func}`polaris.model_step.make_graph_file()` to produce a graph file
from an MPAS mesh file.  Optionally, you can provide the name of an MPAS field 
on cells in the mesh file that gives different weight to different cells
(`weight_field`) in the partitioning process.
