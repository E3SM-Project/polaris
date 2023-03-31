(dev-ocean-framework)=

# Ocean framework

The `ocean` component contains an ever expanding set of shared framework code.

(dev-ocean-model)=

## Model

### Running an E3SM component

Steps that run either Omega or MPAS-Ocean should descend from the
{py:class}`polaris.ocean.model.OceanModelStep` class.  This class descends
from {py:class}`polaris.ModelStep`, so there is a lot of relevant
discussion in {ref}`dev-model`.

#### YAML files vs. namelists and streams

In order to have the same test cases support Omega or MPAS-Ocean, we we want
to be able to produce either the YAML config files used by Omega or the
namelists and streams files used by MPAS-Ocean.  To support both, we decided
that polaris would use Omega-style YAML files to configure all test cases and
convert to MPAS-Ocean's namelists and streams files if needed when steps get
set up.

As a result, the `add_namelist_file()` and `add_streams_file()` methods should
not be used for ocean model steps (they will raise errors).  Similarly,
{py:meth}`polaris.ModelStep.update_yaml_at_runtime()`, 
{py:meth}`polaris.ModelStep.update_namelist_at_runtime()` and
{py:meth}`polaris.ModelStep.update_streams_at_runtime()` should not be 
used  directly but instead should be accessed through
{py:meth}`polaris.ocean.model.OceanModelStep.update_model_config_at_runtime()`.
This method will call the appropriate method depending on whether the test has
been set up for Omega or MPAS-Ocean.

#### Mapping from Omega to MPAS-Ocean config options

As the Omega component is in very early stages of development, we don't yet
know whether Omega's config options will always have the same names as the
corresponding namelist options in MPAS-Ocean.  To support the possibility
that they are different, the 
{py:meth}`polaris.ocean.model.OceanModelStep.map_yaml_to_namelist()` method
can be used to translate names of Omega config options to their MPAS-Ocean
counterparts.

#### Setting MPI resources

The target and minimum number of MPI tasks (`ntasks` and `min_tasks`, 
respectively) are set automatically if the `cell_count` attribute in in the
ocean model step is set to an approximate number of cells in the mesh.
Sometimes, the number of cells in the mesh is known at setup time (e.g. for
regularly spaced planar meshes, where the number of cells is provided 
explicitly).  Often, this is not possible and a more heuristic approach is
needed to estimate the number of cells.  The right approach will need to be 
determined on a test case by test case basis.

