(dev-mesh-feature-masks)=

# Feature Masks

The {py:mod}`polaris.tasks.mesh.spherical.feature_masks` package provides the
model-neutral implementation for creating region or transect masks on standard
MPAS meshes.

The mesh component owns only standard MPAS behavior:

- {py:class}`polaris.tasks.mesh.spherical.feature_masks.ComputeFeatureMasksStep`
  opens a standard MPAS mesh with `xarray`;
- helper functions build the feature collection, detect whether it contains
  regions or transects, validate mask types, and dispatch to `mpas_tools`;
- output files use standard `mpas_tools` region/transect mask conventions.

The mesh package must not contain Omega-specific translation. Ocean-native
input support lives in {py:mod}`polaris.tasks.ocean.feature_masks`, where
{py:class}`polaris.tasks.ocean.feature_masks.ComputeOceanFeatureMasksStep`
subclasses the mesh step and overrides mesh opening and mask writing through
the ocean component's native I/O translation. See {ref}`dev-ocean-feature-masks`.

## Shared Steps

Use
{py:func}`polaris.tasks.mesh.spherical.feature_masks.get_feature_mask_steps`
when another mesh workflow already has an upstream mesh-producing step. The
caller provides:

- `mesh_name`, used for output filenames and metadata;
- `mask_group`, passed to `get_aggregator_by_name()`;
- `mesh_step` and `mesh_filename`, when the mesh is produced by another step.

The shared step does not special-case base meshes or culled meshes.  Workflows
such as E3SM init should pass the relevant upstream step and filename
explicitly.

## Implementation Map

{py:class}`polaris.tasks.mesh.spherical.feature_masks.FeatureMasksTask`
registers the configurable task at
`mesh/spherical/feature_masks/configurable`.

{py:func}`polaris.tasks.mesh.spherical.feature_masks.build_mask_feature_collection`
uses `geometric_features.get_aggregator_by_name()` to build the feature
collection and return the filename prefix and date stamp.

{py:func}`polaris.tasks.mesh.spherical.feature_masks.get_feature_object_type`
validates that the collection contains only regions or only transects.

{py:func}`polaris.tasks.mesh.spherical.feature_masks.compute_feature_masks`
dispatches to `mpas_tools.mesh.mask.compute_mpas_region_masks()` or
`mpas_tools.mesh.mask.compute_mpas_transect_masks()`.

## Testing

Unit tests cover object-type detection, mask-type validation, shared-step
configuration, configurable setup, output metadata, and the ocean subclass's
Omega-name translation boundary.
