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

Some polaris test cases take advantage of the fact that the
[MPAS-Tools cell culler](http://mpas-dev.github.io/MPAS-Tools/stable/mesh_conversion.html#cell-culler)
can produce a graph file as part of the process of culling cells from an
MPAS mesh.  In test cases that do not require cells to be culled, you can
call {py:func}`polaris.model_step.make_graph_file()` to produce a graph file
from an MPAS mesh file.  Optionally, you can provide the name of an MPAS field 
on cells in the mesh file that gives different weight to different cells
(`weight_field`) in the partitioning process.
