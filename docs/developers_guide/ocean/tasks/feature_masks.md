(dev-ocean-feature-masks)=

# Feature Masks

The {py:mod}`polaris.tasks.ocean.feature_masks` package contains the
ocean-specific feature-mask task and step. It exists so native ocean I/O
translation, in particular Omega mesh-name translation, stays in the ocean
framework rather than in the model-neutral mesh component.

This page covers only the ocean-specific extension. The shared mask-generation
design, helper functions, and standard MPAS output conventions are documented
in {ref}`dev-mesh-feature-masks`.

{py:class}`polaris.tasks.ocean.feature_masks.ComputeOceanFeatureMasksStep`
subclasses the mesh component's
{py:class}`polaris.tasks.mesh.spherical.feature_masks.ComputeFeatureMasksStep`
and overrides the model-specific I/O hooks:

- standard MPAS-Ocean input passes through unchanged;
- Omega-format mesh input is mapped to MPAS-Ocean names with
  {py:meth}`polaris.tasks.ocean.Ocean.open_model_dataset`;
- mask computation is delegated to the shared, model-neutral mesh helpers
  documented in {ref}`dev-mesh-feature-masks`;
- mask output is mapped back to native ocean names, such as `NCells`,
  `NEdges`, `NRegions`, and `RegionCellMasks` for Omega.

{py:class}`polaris.tasks.ocean.feature_masks.OceanFeatureMasksTask` registers
the configurable task at `ocean/feature_masks/configurable`. It uses the same
`[feature_masks]` config section as the mesh task and swaps in the ocean step
class so ocean model detection and native I/O translation are available during
setup and run.

Future Omega-friendly output naming or variable filtering should also stay in
this ocean package, not in {py:mod}`polaris.tasks.mesh.spherical.feature_masks`.

## MOC Basins Extension

`ComputeOceanFeatureMasksStep` overrides two protected hooks to handle the
`'MOC Basins'` mask group as a special case.

**`_set_output_filenames(mesh_name, mask_group)`** — calls `super()` to set
the normal filenames and then, for `mask_group == 'MOC Basins'`, replaces
`output_filename` with `{mesh_name}_mocBasinsAndTransects{date}.nc`.
`geojson_filename` is left as `mocBasins{date}.geojson` (the intermediate
GeoJSON used by `compute_mpas_region_masks`).  The renamed output matches the
convention expected by MPAS-Analysis.

**`_post_process_masks(ds_masks, ds_mesh, mask_group)`** — for
`mask_group == 'MOC Basins'`, calls
`mpas_tools.ocean.moc.add_moc_southern_boundary_transects(ds_masks, ds_mesh,
logger=self.logger)`, which appends southern-boundary transect masks derived
algorithmically from the basin cell masks.  The string variables `'history'`
and `'constituents'`, which `add_moc_southern_boundary_transects` may attach
and which are incompatible with CDF5 output, are dropped if present.  For all
other mask groups the method is a no-op.

The hook is defined on the model-neutral base class
{py:class}`polaris.tasks.mesh.spherical.feature_masks.ComputeFeatureMasksStep`
as a no-op return; `add_moc_southern_boundary_transects` lives in
`mpas_tools.ocean` and must not be imported by the mesh package.
