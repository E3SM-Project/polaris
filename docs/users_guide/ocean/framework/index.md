(ocean-framework)=

# Framework

The ocean component includes a small amount of framework code that is shared 
across tasks.

```{toctree}
:titlesonly: true

vertical
ice_shelf
```

## Tracer conventions

Under the TEOS-10 equation of state (`ocean:eos_type = teos-10`), Omega's
`temperature` and `salinity` are conservative temperature and absolute
salinity while MPAS-Ocean's are potential temperature and practical
salinity.  Polaris converts the tracers of an initial condition to the
convention of whichever model is being run.  For the other equations of
state, both models apply the same formula and no conversion takes place.

Converting absolute to practical salinity (and back) depends slightly on
where in the ocean the water is.  On a spherical mesh, each cell is
converted at its own location.  A planar mesh has no location, so these
config options are used instead:

```cfg
# Options related the ocean component
[ocean]

# Nominal location (degrees) of a planar mesh, used to convert between
# absolute and practical salinity.  Planar meshes have no geographic location
# but the conversion is only weakly dependent on it, so tasks only need to
# override these values if they have a location in mind.
nominal_lon = 0.0
nominal_lat = 0.0
```

The correction is at most about 0.02 g/kg anywhere in the global ocean, so
the default location is harmless for idealized tasks.
