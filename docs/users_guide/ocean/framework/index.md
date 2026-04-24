(ocean-framework)=

# Framework

The ocean component includes a small amount of framework code that is shared
across tasks.

For tasks that support both MPAS-Ocean and Omega, Polaris stages the
horizontal mesh and initial state as separate model inputs. The
`[ocean_model_files]` config section controls the local filenames. The
defaults are:

```cfg
[ocean_model_files]
horiz_mesh_filename = mesh.nc
init_filename = init.nc
```
Most users should leave these defaults alone. Advanced users can override them,
but this must be done a setup time (e.g. with a user config file), not in the
work directory at which point it is too late to change these files. The
typical reason to do so would be degugging in circumstances where the
MPAS-Ocean or Omega branch is not prepared for separate mesh and initial
condition files.


```{toctree}
:titlesonly: true

vertical
ice_shelf
```
