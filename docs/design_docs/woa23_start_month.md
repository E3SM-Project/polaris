# WOA23 Hydrography for Any Start Month

Creation date: 2026/09/25

Contributors:

- Xylar Asay-Davis
- Claude

## Summary

The `hydrography/woa23` task builds a reusable WOA23 temperature and salinity
product for initializing realistic global ocean simulations. It currently uses
the January climatology above 1500 m, which is only right for simulations that
start on January 1. E3SM also needs simulations that start on October 1, and
rather than hard-coding a second month, this design makes the month a config
option.

The complication is caching. The combine and extrapolate steps are expensive
enough that their outputs are cached, and a cached product for one month must
never be used for another. The design gives each month its own cache entry,
caches all 12 months, and has every product record the month it represents.
Downstream initialization and forward tasks can then use that record to set a
consistent initial-condition `Time` and simulation start date. That work is
outside the scope of this design.

Success means the task produces a correct product for any month, a cached
product is always the one for the configured month, and all 12 months are
available from the cache.

## Requirements

### Requirement: Any month can be selected

Date last modified: 2026/09/25

Contributors:

- Xylar Asay-Davis
- Claude

The WOA23 product shall be buildable for any month of the year, selected with
a config option. January shall be the default.

### Requirement: Cached products match the configured month

Date last modified: 2026/09/25

Contributors:

- Xylar Asay-Davis
- Claude

A cached product shall only be used for the month it was built for. If a
cached product is requested for a month that has no cache entry, setup shall
fail rather than run the step or use another month's product.

### Requirement: Products record their month

Date last modified: 2026/09/25

Contributors:

- Xylar Asay-Davis
- Claude

Each product shall record which month it represents, so downstream steps can
check or derive the simulation start date from it.

### Requirement: All 12 months are cached affordably

Date last modified: 2026/09/25

Contributors:

- Xylar Asay-Davis
- Claude

Products for all 12 months shall be available from the cache. A machine that
uses one month shall not have to download the others.

## Algorithm Design

### Algorithm Design: Any month can be selected

Date last modified: 2026/09/25

Contributors:

- Xylar Asay-Davis
- Claude

WOA23 monthly climatologies (`t01`–`t12`, `s01`–`s12`) cover the upper 57
depth levels, down to 1500 m. The annual climatology fills the levels below.
This is the existing January algorithm with a different month's files.
An October 1 start uses the October mean, the same convention by which a
January 1 start uses the January mean.

### Algorithm Design: All 12 months are cached affordably

Date last modified: 2026/09/25

Contributors:

- Xylar Asay-Davis
- Claude

The January products in the cache are 1.7 GB each (combined and extrapolated),
written as double precision. The WOA23 source is single precision, so writing
the products as single precision loses nothing and halves their size. All 12
months then take about 20 GB in the cache. Keeping one file per month means
each machine downloads only the months it uses.

## Implementation

### Implementation: Any month can be selected

Date last modified: 2026/09/25

Contributors:

- Xylar Asay-Davis
- Claude

A new option `[woa23] month` takes an integer from 1 to 12. Because the month
is a config option, it is read when steps are set up, not when they are
constructed. There is one month per work directory, since every mesh shares
the WOA23 steps.

### Implementation: Cached products match the configured month

Date last modified: 2026/09/25

Contributors:

- Xylar Asay-Davis
- Claude

The month is part of both output filenames, `woa_combined_<mon>.nc` and
`woa23_decav_0.25_<mon>_extrap.nc`, where `<mon>` is a lowercase
three-letter abbreviation. The filenames are declared in `setup()`, once the
config is available. Cache entries are keyed by the path of each output in the
work directory, so each month is a separate entry.

A step that is cached for a month with no entry already fails at setup with
Polaris' "has not been added to the cache database" error. That applies whether
the step was cached explicitly or by default. There is deliberately no
fallback to running the step: running quietly could hide a missing cache entry.
`--free_running` runs such a step explicitly.

Downstream steps get these filenames from the WOA23 steps, not from a
constant.

### Implementation: Products record their month

Date last modified: 2026/09/25

Contributors:

- Xylar Asay-Davis
- Claude

Both products carry a global attribute `month` with the integer month.

### Implementation: All 12 months are cached affordably

Date last modified: 2026/09/25

Contributors:

- Xylar Asay-Davis
- Claude

Temperature and salinity are computed in double precision and cast to single
precision only when the products are written. `polaris/ocean/cached_files.json`
gets one entry per month for each of the two steps. The January entries are
regenerated rather than renamed, since the new products differ from the old
ones at single-precision round-off.

## Testing

### Testing and Validation: Any month can be selected

Date last modified: 2026/09/25

Contributors:

- Xylar Asay-Davis
- Claude

Unit tests check the mapping from month to WOA23 source files and to output
filenames, and that months outside 1–12 are rejected. The task is run for all
12 months on Chrysalis, and the `viz` output is inspected for each.

### Testing and Validation: Cached products match the configured month

Date last modified: 2026/09/25

Contributors:

- Xylar Asay-Davis
- Claude

A unit test checks that a cached step for a month with no cache entry fails
at setup.

### Testing and Validation: Products record their month

Date last modified: 2026/09/25

Contributors:

- Xylar Asay-Davis
- Claude

The 12 products are checked for the right `month` attribute.

### Testing and Validation: All 12 months are cached affordably

Date last modified: 2026/09/25

Contributors:

- Xylar Asay-Davis
- Claude

The new January extrapolated product is compared with the existing
double-precision cache entry. The two should agree to single-precision
round-off.
