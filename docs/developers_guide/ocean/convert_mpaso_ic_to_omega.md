(dev-ocean-convert-mpaso-ic-to-omega)=

# convert_mpaso_ic_to_omega.py

The script `utils/omega/convert_mpaso_ic_to_omega.py` is a developer utility
for converting an MPAS-Ocean initial-condition file into an Omega-formatted
initial-condition file.  It is primarily intended for cases where a developer
already has an MPAS-Ocean initial condition and needs a corresponding Omega
file with the expected variable names, a `PseudoThickness` field, and optional
tracer conversion for the requested equation of state.

The script complements the model-variable mapping described in
{ref}`dev-ocean-model`.  In contrast to
{py:meth}`polaris.ocean.model.OceanIOStep.write_model_dataset`, which maps
datasets during task setup, this utility performs a one-time conversion of an
existing NetCDF file on disk.

## Workflow

The converter performs the following operations:

1. It loads the MPAS-Ocean initial condition from `--input-file`.
2. It writes a zero-velocity MPAS-style companion file with the suffix
   `.mpas.nc`.
3. It rescales spherical coordinates and areas to the Polaris Earth radius
   from `pcd.yaml`.
4. It converts tracers according to `--eos-type`:

   - `teos10` converts potential temperature to conservative temperature and
     practical salinity to absolute salinity.
   - `linear` leaves temperature and salinity unchanged and computes specific
     volume from the linear EOS coefficients used by Omega.

5. It computes `PseudoThickness` from `layerThickness`, the reference seawater
   density, and specific volume.
6. It zeros any numeric fields whose names contain `velocity`.
7. It renames dimensions and variables using
   `polaris/ocean/model/mpaso_to_omega.yaml`.
8. It writes the converted Omega file with
   {py:func}`mpas_tools.io.write_netcdf`.

If `--visualization` is supplied, the script also writes diagnostic figures for
the converted temperature and salinity fields before the final rename to Omega
variable names.  The temperature diagnostic is an absolute difference
(`Omega - MPAS-Ocean`) and the salinity diagnostic is a percent difference.

## Command-Line Interface

Typical TEOS-10 usage is:

```bash
python utils/omega/convert_mpaso_ic_to_omega.py \
    --input-file /path/to/ocean.nc \
    --output-file /path/to/ocean.omega.nc \
    --eos-type teos10
```

To also write the comparison figures:

```bash
python utils/omega/convert_mpaso_ic_to_omega.py \
    --input-file /path/to/ocean.nc \
    --output-file /path/to/ocean.omega.nc \
    --eos-type teos10 \
    --visualization
```

For linear-EOS testing, use:

```bash
python utils/omega/convert_mpaso_ic_to_omega.py \
    --input-file /path/to/ocean.nc \
    --output-file /path/to/ocean.omega.nc \
    --eos-type linear
```

The script appends an EOS suffix automatically unless it is already present:

- `teos10` produces `*.teos10eos.nc`
- `linear` produces `*.lineareos.nc`

## Input Expectations

At a minimum, the input file must contain `layerThickness`.  For TEOS-10
conversion, the script also requires `temperature`, `salinity`, `latCell`, and
`lonCell`.  The implementation assumes the standard MPAS-Ocean dimensions
`Time`, `nCells`, and `nVertLevels`.

When TEOS-10 conversion is enabled, the script estimates mid-layer pressure by
integrating hydrostatically downward from the surface.  If present,
`atmosphericPressure` and `seaIcePressure` are included in the surface pressure
used for this integration.

## Outputs

The converter can produce up to four artifacts:

- An MPAS-style file with zeroed velocity fields, written next to the input
  file with the suffix `.mpas.nc`
- An Omega-formatted initial condition written next to the requested output
  path with an EOS-specific suffix
- A temperature comparison figure named
  `<output_stem>_temperature_absolute_difference.png` when
  `--visualization` is enabled
- A salinity comparison figure named
  `<output_stem>_salinity_percent_difference.png` when `--visualization` is
  enabled

## Implementation Notes

The renaming logic for dimensions and variables is shared with the ocean model
support described in {ref}`dev-ocean-model`.  If new Omega variables, config
options, or dimensions are added, update
`polaris/ocean/model/mpaso_to_omega.yaml` so the standalone converter and the
task-based model I/O remain consistent.

The script is intentionally separate from the task framework because it is
useful during dataset preparation and debugging outside the lifecycle of a
Polaris task or step.