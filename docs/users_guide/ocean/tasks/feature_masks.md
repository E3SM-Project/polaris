(users-ocean-feature-masks)=

# Feature Masks

The `ocean/feature_masks/configurable` task creates standard MPAS mask files on
an existing native ocean mesh.  It uses the same `[feature_masks]` options as
the mesh-component feature-mask task, including `mesh_filename`, `mesh_name`,
and `mask_group`; see {ref}`users-mesh-feature-masks` for the common mask
behavior and output conventions.

This ocean task is the place to use Omega-format mesh input.  The step opens
the mesh through the ocean component's model I/O layer, so Omega variable and
dimension names are translated back to standard MPAS-Ocean names before mask
creation.  For Omega, the mask output is then mapped back to native names,
such as `NCells`, `NEdges`, `NRegions`, and `RegionCellMasks`.

Use the mesh-component task instead when the input file is already a standard
MPAS mesh and no ocean-model-specific I/O translation is needed.

## MOC Basins

When `mask_group = MOC Basins`, the step performs an extra post-processing pass
after the normal region-mask computation.
`mpas_tools.ocean.moc.add_moc_southern_boundary_transects` is called with the
basin cell masks and the mesh dataset to derive southern-boundary transect masks
for each MOC basin; these are appended to the output dataset alongside the
region masks.

The output file is named `{mesh_name}_mocBasinsAndTransects{date}.nc` (instead
of the normal `{mesh_name}_mocBasins{date}.nc`) so downstream tools such as
MPAS-Analysis can locate the combined file.

## Example

```bash
polaris setup -t ocean/feature_masks/configurable -w ocean_feature_masks
```

Edit `ocean_feature_masks/ocean/feature_masks/configurable/feature_masks.cfg`
to point at the mesh file and select the mask group, then run the task.
Missing required options are reported when the task runs, after the work-dir
config has been edited.
