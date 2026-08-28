(dev-mesh)=

# Mesh component

The `mesh` component defines tasks and steps related to generating and
manipulating MPAS meshes.  There are currently no component-level config
options.

The code is split between two packages:

- `polaris.tasks.mesh` holds the tasks and steps of the component itself,
  described in {ref}`dev-mesh-tasks`.  These are the base-mesh tasks and the
  unified-mesh task families.
- `polaris.mesh` holds the shared mesh framework, described in
  {ref}`dev-mesh-framework`.  Despite living under the mesh component in these
  docs, it is imported by the `ocean` and `e3sm/init` components as well, so
  changes to it need to be made with those callers in mind.

```{toctree}
:titlesonly: true

tasks/index
framework/index
```
