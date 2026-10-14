(dev-mpas)=

# MPAS

The module `polaris.mpas` has some helper functions that are handy for
working with output from MPAS components.

## Area

The function {py:func}`polaris.mpas.area_for_field()` is handy for getting
the right area (on cells, edges or vertices) associated with a given field in 
an MPAS output file.  This function determines from the dimensions of the
given field which area is appropriate.  This is useful in computing
integrals or other area-weighted statistics.

Example usage in an error calculation:

```python
import numpy as np
import xarray as xr
from polaris.mpas import area_for_field


def compute_error(field_exact, field_mpas, mesh_filename):
    ds_mesh = xr.open_dataset(mesh_filename)
    
    diff = field_exact - field_mpas
    area = area_for_field(ds_mesh, diff)
    total_area = np.sum(area)
    den_l2 = np.sum(field_exact**2 * area) / total_area
    num_l2 = np.sum(diff**2 * area) / total_area
    error = np.sqrt(num_l2) / np.sqrt(den_l2)
    return error
```

## Time

The function {py:func}`polaris.mpas.time_index_from_xtime()` can be used to
find the time index closest to a requested time interval in seconds from a 
given start time.  The default start time is the first time in the array of
`xtime` values, but a different string can be supplied instead (e.g. if the
start time isn't included in the output file).

Example usage for extracting a field at a given time from an MPAS output file:

```python
import xarray as xr
from polaris.mpas import time_index_from_xtime


def get_output_field(field_name, time, output_filename):
    ds_out = xr.open_dataset(output_filename)

    time_index = time_index_from_xtime(ds_out.xtime.values, time)
    ds_out = ds_out.isel(Time=time_index)
    field_mpas = ds_out[field_name]
    return field_mpas
```