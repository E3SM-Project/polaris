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
