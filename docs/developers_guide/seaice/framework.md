(dev-seaice-framework)=

# Seaice framework

The `seaice` component contains an ever expanding set of shared framework code.

(dev-seaice-model)=

## Model

### Running an E3SM component

Steps that run MPAS-Seaice should descend from the
{py:class}`polaris.seaice.model.SeaiceModelStep` class.  This class descends
from {py:class}`polaris.ModelStep`, see {ref}`dev-model`.


#### Setting MPI resources

The MPAS-Seaice tests currently only include single column test cases. 
Therefore, there is no concern for setting MPI resources. This may change
as more complicates test cases are included.

(dev-seaice-framework-config)=

## Model config options and streams

There is currently no generic module setup for MPAS-Seaice model config options. 
The namelist and streams files are located within each test group and/or case.

