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

In order to have the same test cases support Omega or MPAS-Ocean, we want
to be able to produce either the YAML config files used by Omega or the
namelists and streams files used by MPAS-Ocean.  To support both, we decided
that polaris would use Omega-style YAML files to configure all ocean test cases
and convert to MPAS-Ocean's namelists and streams files if needed when steps
get set up.

As a result, the `add_namelist_file()` and `add_streams_file()` methods should
not be used for ocean model steps (they will raise errors).

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
respectively) are set automatically if `ntasks` and `min_tasks` have not
already been set explicitly.  In such cases, a subclass of `OceanModelStep`
must override the
{py:meth}`polaris.ocean.model.OceanModelStep.compute_cell_count()` method
to compute the number of cells in the mesh.  Since it is typically not possible
to read the cell count from a file during setup, this method may need to have
a heuristic way of approximating the number of cells during setup (i.e. when
the `at_setup` parameter is `True`.  Then, it can return the exact number of 
cells at runtime (i.e. `at_setup == False`).
