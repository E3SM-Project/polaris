(dev-seaice-mpas-seaice)=

# Supported Model: MPAS-Seaice

The following are considerations that may be useful in developing a new task for MPAS-Seaice.

## Initial conditions

MPAS-Seaice has no specific requirements for defining the sea ice initial conditions. 
The current default setting for the single column tasks is a solid 1m thick disc 
of sea ice that covers the single-grid cell domain.  
The MPAS-Seaice initial conditions are defined in the default namelist file contained 
within the component directory: 
`e3sm_submodules/E3SM-Project/components/mpas-seaice/namelist.seaice`

The 1m thick sea ice disc (the default initial conditions) are set through the following 
config options within in the namelist file:
```
&initialize
    config_initial_ice_area = 1.0
    config_initial_ice_volume = 1.0
```

To define alternative sea ice initial conditions, modifications should be made to the
namelist file placed within the task directory. 


## Forcing

The default forcing for MPAS-Seaice is CORE forcing beginning on 2000-01-01_00:00:00.
These default settings are defined in the namelist file within the component directory:
`e3sm_submodules/E3SM-Project/components/mpas-seaice/namelist.seaice`

```
&forcing
    config_atmospheric_forcing_type = 'CORE'
    config_forcing_start_time = '2000-01-01_00:00:00'
    config_forcing_cycle_start = '2000-01-01_00:00:00'
    config_forcing_cycle_duration = '2-00-00_00:00:00'
    config_forcing_precipitation_units = 'mm_per_sec'
    config_forcing_sst_type = 'ncar'
    config_update_ocean_fluxes = false
    config_include_pond_freshwater_feedback = false
/
```

If modifications to the forcing are needed for tasks, they should be added to
the namelist file placed within the task directory.
