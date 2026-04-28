(dev-mesh-tasks)=

# Tasks

(dev-mesh-base-mesh-task)=

## Base Mesh Task

The the base mesh tasks defined by {py:class}`polaris.tasks.mesh.base.BaseMeshTask`
can be used to generate quasi-uniform (`qu`) and subdivided icosahedral
(`icos`) spherical meshes at quasi-uniform resolutions ranging from 30 to 480
km.  These "base" meshes cover the full sphere (include both continents and
ocean regions).

## Unified Mesh Preparation Tasks

This section covers the shared task families that prepare reusable coastline
and river products for named global unified meshes. These workflows are
intended to be reused by downstream sizing-field and base-mesh tasks rather
than implemented separately inside each consumer.

```{toctree}
:titlesonly: true

unified/coastline
unified/river
```
