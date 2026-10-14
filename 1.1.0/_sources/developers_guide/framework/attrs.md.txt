(dev-attrs)=

# Variable attributes

Fields Polaris writes to a NetCDF file should say what they are: a
`long_name`, and `units` where the quantity has a meaningful unit.  Getting
that right takes a little care, because a variable computed from another one
does not start out with a blank slate.

(dev-attrs-inheritance)=

## xarray propagates attributes

xarray keeps `attrs` through binary arithmetic, comparisons, `where()`,
`zeros_like()` and NumPy ufuncs such as `np.maximum`:

```python
>>> bottom_pressure.attrs
{'long_name': 'seafloor pressure', 'units': 'Pa'}
>>> (bottom_pressure / (rho0 * gravity)).attrs
{'long_name': 'seafloor pressure', 'units': 'Pa'}
>>> xr.zeros_like(bottom_pressure).astype(int).attrs
{'long_name': 'seafloor pressure', 'units': 'Pa'}
```

A depth in meters and a one-based level index both come out of that claiming
to be a pressure in Pascals.  Older versions of xarray dropped attributes in
arithmetic, so code written against that behaviour changed meaning silently on
upgrade.

Setting individual keys is not enough to undo it:

```python
# leaves any other attribute the parent had, such as a stale
# ``cell_measures`` or a non-standard ``unit``
ds.bottomDepth.attrs['long_name'] = 'seafloor geometric depth'
ds.bottomDepth.attrs['units'] = 'm'
```

Nor is `xr.set_options(keep_attrs=False)`: it suppresses propagation through
arithmetic and comparisons, but `zeros_like()` and `where()` keep attributes
regardless.

(dev-attrs-set-attrs)=

## Use `set_attrs()`

{py:func}`polaris.attrs.set_attrs()` replaces a variable's attributes
wholesale, so a field carries exactly what it is given and nothing it
inherited:

```python
from polaris.attrs import set_attrs

# in place, on a variable already in a dataset
ds['maxLevelCell'] = max_level_cell + 1
set_attrs(
    ds.maxLevelCell,
    long_name='Index to the last active ocean cell in each column.',
)

# inline, on an expression
ds['bottomDepth'] = set_attrs(
    -geom_z_bot, long_name='seafloor geometric depth', units='m'
)
```

Both patterns work: `set_attrs()` modifies the array in place and returns it.
`ds[name]` shares the underlying `Variable`, so labelling `ds.maxLevelCell`
reaches the dataset; and `ds[name] = da` copies the attributes, so two dataset
variables built from one array can still describe themselves differently.

Leave `units` out for quantities that have no meaningful unit — a one-based
level index, a boolean mask — rather than inventing one.  Anything else, such
as a `note` or a `standard_name`, can be passed as an extra keyword argument.
