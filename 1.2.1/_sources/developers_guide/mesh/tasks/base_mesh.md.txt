(dev-mesh-base-mesh-task)=

# Base Mesh Tasks

The base mesh tasks defined by
{py:class}`polaris.tasks.mesh.base.BaseMeshTask` can be used to generate
quasi-uniform (`qu`) and subdivided icosahedral (`icos`) spherical meshes at
quasi-uniform resolutions ranging from 30 to 480 km.  These base meshes cover
the full sphere, including both continents and ocean regions.

The same task family also includes the supported variable-resolution base
meshes such as `rrs6to18km` and `so12to30km`.
