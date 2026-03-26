(ocean-global-ocean)=

# global_ocean

This category contains ocean preprocessing tasks that are upstream of any
particular MPAS mesh. The first task builds a reusable World Ocean Atlas 2023
(WOA23) hydrography product on the native 0.25-degree latitude-longitude grid.

## supported models

This task is model-independent and does not require either MPAS-Ocean or
Omega to be built.

(ocean-global-ocean-woa23)=

## woa23

This task is the Polaris port of the legacy Compass
`utility/extrap_woa` workflow. It combines January and annual WOA23
climatologies, uses a cached `e3sm/init` combined-topography product on the
WOA grid to define the ocean mask used during preprocessing, and then fills
missing temperature and salinity values through staged horizontal and vertical
extrapolation.

The task can be set up with:

```bash
polaris setup -t ocean/global_ocean/hydrography/woa23 ...
```

### description

The task is organized into three inspectable steps:

1. `combine_topo` reuses a cached `e3sm/init` combined-topography step
   configured for the WOA23 0.25-degree latitude-longitude grid.
2. `combine` creates `woa_combined.nc` by combining January and annual WOA23
   fields and converting temperature to potential temperature.
3. `extrapolate` creates the final
   `woa23_decav_0.25_jan_extrap.nc` product.

This layout is intended to match Polaris shared-step conventions so the WOA23
preprocessing pipeline can later be reused by mesh-dependent
`global_ocean` initialization tasks.

### mesh

N/A. This task operates on the native WOA23 latitude-longitude grid rather
than an MPAS mesh.

### vertical grid

N/A. The task preserves the standard WOA23 depth levels.

### initial conditions

The source fields come from the WOA23 January and annual climatologies in the
Polaris input database.

### forcing

N/A.

### time step and run duration

N/A.

### config options

```cfg
# Options related to generating a reusable WOA23 hydrography product
[woa23]

# the minimum weight sum needed to mark a new cell valid in horizontal
# extrapolation
extrap_threshold = 0.01
```

### cores

The local `combine` and `extrapolate` steps run serially. The
`combine_topo` step is intended to use the cached `e3sm/init` output because
regenerating the combined topography product is substantially more expensive.
