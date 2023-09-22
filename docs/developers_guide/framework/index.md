(dev-framework)=

# Framework

All of the {ref}`dev-packages` that are not in the two components (`ocean`
and `seaice`) belong to the polaris framework.  Some of these
modules and packages are used by the {ref}`dev-command-line`, while others are
meant to be called within tasks and steps to simplify tasks like adding
input and output files, downloading data sets, building up config files,
yaml files, namelists and streams files, setting up and running the E3SM 
component, and  verifying the output by comparing steps with one another or 
against a baseline.

```{toctree}
:titlesonly: true

commands
config
logging
io
mesh
model
provenance
remapping
validation
visualization
```
