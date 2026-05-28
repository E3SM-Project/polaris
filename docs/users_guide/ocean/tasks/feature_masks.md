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
creation.  For Omega, mesh dimensions in the mask output, such as `NCells`
and `NEdges`, are mapped back to native names.  Region and transect
dimensions and mask variables keep their MPAS names, since Omega does not yet
define names for them.

Use the mesh-component task instead when the input file is already a standard
MPAS mesh and no ocean-model-specific I/O translation is needed.

## Example

```bash
polaris setup -t ocean/feature_masks/configurable -w ocean_feature_masks
```

Edit `ocean_feature_masks/ocean/feature_masks/configurable/feature_masks.cfg`
to point at the mesh file and select the mask group, then run the task.
Missing required options are reported when the task runs, after the work-dir
config has been edited.
