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

(dev-mesh-feature-masks-moc)=

## MOC Helpers

{py:mod}`polaris.tasks.mesh.spherical.feature_masks.moc` is a leaf module
holding the two pieces of `'MOC Basins'` behavior that are not specific to any
model:

- {py:func}`polaris.tasks.mesh.spherical.feature_masks.moc.moc_masks_filename`
  applies the `mocBasinsAndTransects` filename convention that E3SM already
  uses, as in `oRRS18to6v3_mocBasinsAndTransects20210623.nc`;
- {py:func}`polaris.tasks.mesh.spherical.feature_masks.moc.add_moc_transects`
  calls `mpas_tools.ocean.moc.add_moc_southern_boundary_transects()` to append
  southern-boundary transect masks derived algorithmically from the basin cell
  masks, then drops the string variables `'history'` and `'constituents'`,
  which that function may attach and which are incompatible with CDF5 output.

The module also defines `MOC_MASK_GROUP` (`'MOC Basins'`) and `MOC_PREFIX`
(`'mocBasinsAndTransects'`).

Neither helper needs a step, and neither touches an ocean model: they operate
on standard MPAS meshes and masks.  `mpas_tools.ocean.moc` is a plain
`mpas_tools` module, so importing it does not pull in
{py:mod}`polaris.tasks.ocean` or require an `[ocean]` config section.  That is
what lets a step in another component — for example the `e3sm/init`
`component_inputs` staging of the per-mesh MOC file that MPAS-Ocean reads
through its `regionalMasksInput` and `transectMasksInput` streams — subclass
the model-neutral {py:class}`polaris.tasks.mesh.spherical.feature_masks.ComputeFeatureMasksStep`
and call the same two functions.

{py:class}`polaris.tasks.ocean.feature_masks.ComputeOceanFeatureMasksStep`
delegates to these helpers rather than implementing the behavior itself, so
the MOC logic lives in exactly one place.  See
{ref}`dev-ocean-feature-masks`.

## Testing

Unit tests cover object-type detection, mask-type validation, shared-step
configuration, configurable setup, output metadata, the MOC helpers (including
that importing the `moc` module does not import
{py:mod}`polaris.tasks.ocean`), and the ocean subclass's Omega-name
translation boundary.
