(dev-mesh-info)=

# Mesh Information

Both spherical and planar MPAS meshes are described by the same variables, so
code that needs to tell them apart has to look at the `on_a_sphere` global
attribute, which is always either `'YES'` or `'NO'`.  Rather than comparing
against that attribute directly, use
{py:func}`polaris.mesh.info.is_spherical()` or
{py:func}`polaris.mesh.info.is_planar()`:

```python
from polaris.mesh.info import is_planar


if is_planar(ds_mesh):
    # on a planar mesh, the x and y axes are the "zonal" and "meridional"
    # directions
    ...
```

A dataset with no `on_a_sphere` attribute is invalid, and assuming either
answer leads to results that are silently wrong (a global ocean treated as a
planar domain, say), so both functions raise a `ValueError` in that case.  A
caller that knows better -- a step assembling a dataset that has not picked
up the attribute yet, for example -- can pass an explicit `default`:

```python
# an initial condition under construction may not have the attribute yet,
# in which case it is planar
spherical = is_spherical(ds, default=False)
```

An attribute that is present but is neither `'YES'` nor `'NO'` is also a
`ValueError`, since it means the file is garbled rather than planar.
