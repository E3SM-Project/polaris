(dev-ocean-convert-mpaso-ic-to-omega)=

# convert_mpaso_ic_to_omega.py

The script `utils/omega/convert_mpaso_ic_to_omega.py` is a developer utility
for converting an MPAS-Ocean initial-condition file into an Omega-formatted
initial-condition file.  It is primarily intended for cases where a developer
already has an MPAS-Ocean initial condition and needs a corresponding Omega
file with the expected variable names, a `PseudoThickness` field, optional
idealized or ERA5 based surface forcing, and optional
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
3. On a spherical mesh (`on_a_sphere = 'YES'`), it rescales coordinates and
   areas to the Polaris Earth radius from `pcd.yaml`.  Planar meshes are left
   alone.
4. It converts tracers according to `--eos-type`:

   - `teos10` converts potential temperature to conservative temperature and
     practical salinity to absolute salinity.
   - `linear` leaves temperature and salinity unchanged and computes specific
     volume from the linear EOS coefficients used by Omega.

5. It computes `PseudoThickness` from `layerThickness`, the reference seawater
   density, and specific volume.
6. It zeros any numeric fields whose names contain `velocity`.
7. It optionally adds idealized surface stress forcing or surface stress, 
   net heat flux and surface freshwater forcing from a 20 year average of ERA5.
8. It optionally interpolates satellite-derived red and blue band shortwave
   extinction coefficients onto the mesh and adds them to both the MPAS zero-velocity
   companion file and the converted Omega file.
9. It renames dimensions and variables using
   `polaris/ocean/model/mpaso_to_omega.yaml`.
10. It writes the converted Omega file with
   {py:func}`mpas_tools.io.write_netcdf`.

If `--visualization` is supplied, the script also writes diagnostic figures for
the converted temperature and salinity fields before the final rename to Omega
variable names.  Figures are only produced on spherical meshes.  The temperature diagnostic is an absolute difference
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
There are two options for forcing; idealized and a 1990-2010 annual average climatology of ERA5 net surface heat flux, freshwater flux, and momentum fluxes.  The idealized forcing includes surface stress only.  A cubic spline is fit to the following specified stresses

| Latitude ($^o$N) | Sfc Stress (Pa) | 
| :--------------: | :-------------: |
| -70              | 0.0             |
| -45              | 0.2             |
| -15              | -0.1            |
| 0                | -0.02           |
| 15               | -0.1            |
| 45               |  0.1            |
| 70               | 0.0             |

To add this sfc stress to the omega initial condition, add the `--include-idealized-sfc-stress` to the python invocation above.

To instead generate a file with ERA5 based forcing, use:

```bash
python utils/omega/convert_mpaso_ic_to_omega.py \
  --input-file /path/to/ocean_ic_file.nc \
  --output-file /path/to/ocean.omega.nc \
  --eos-type teos10 \
  --include-realistic-forcing
```

On supported machines, this will download the ERA5 forcing file and SCRIP file for interpolation.  If you are running on a non-supported machine you can download the files separately and use the following:

```bash
python utils/omega/convert_mpaso_ic_to_omega.py \
    --input-file /path/to/ocean.nc \
    --output-file /path/to/ocean.omega.nc \
    --eos-type teos10 \
    --include-realistic-forcing \
    --forcing-file /path/to/forcing_file.nc \
    --forcing-scrip-file /path/to/era5_0.25deg_scrip.nc \
```

The forcing file generation uses conservative remapping by default; if you wish to use another method add `--remap-method bilinear` to the command.

### Shortwave Extinction Coefficients

To include red-band and blue-band shortwave extinction coefficients
(`ExtinctionCoeffRed` and `ExtinctionCoeffBlue`) in the converted MPAS companion
file and Omega initial condition, add `--include-shortwave-extinction`:

```bash
python utils/omega/convert_mpaso_ic_to_omega.py \
    --input-file /path/to/ocean.nc \
    --output-file /path/to/ocean.omega.nc \
    --eos-type teos10 \
    --include-shortwave-extinction
```

On supported machines, the shortwave extinction data file
(`shortwave_extinction_0.083x0.083_20261002.nc`) and its corresponding source
SCRIP file (`shortwave_extinction_scrip_20261002.nc`) are automatically
downloaded from the Polaris repository under `ocean/realistic_global/forcing`.
On non-supported machines or to use custom inputs, supply local files:

```bash
python utils/omega/convert_mpaso_ic_to_omega.py \
    --input-file /path/to/ocean.nc \
    --output-file /path/to/ocean.omega.nc \
    --eos-type teos10 \
    --include-shortwave-extinction \
    --shortwave-file /path/to/shortwave_extinction.nc \
    --shortwave-scrip-file /path/to/shortwave_extinction_scrip.nc
```

If you only need a standalone companion file containing `latCell`, `lonCell`,
`ExtinctionCoeffRed`, and `ExtinctionCoeffBlue` for an MPAS mesh rather than
converting an entire initial condition, use the companion utility
`utils/omega/interp_shortwave_extinction_to_mpas.py`:

```bash
python utils/omega/interp_shortwave_extinction_to_mpas.py \
    --mesh /path/to/mpas_mesh.nc \
    --output-file /path/to/shortwave_extinction_on_mesh.nc
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
  file with the suffix `.mpas.nc` (optionally including `ExtinctionCoeffRed`
  and `ExtinctionCoeffBlue` when `--include-shortwave-extinction` is given)
- An Omega-formatted initial condition written next to the requested output
  path with an EOS-specific suffix (optionally including `ExtinctionCoeffRed`
  and `ExtinctionCoeffBlue` mapped to dimension `NCells`)
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