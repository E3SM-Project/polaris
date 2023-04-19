(dev-organization)=

# Organization of Tests

Here, we describe how tests in polaris are organized, both in the package
itself and in the work directories where they get set up and run.  At the base
level are components ({ref}`dev-landice` or {ref}`dev-ocean`).  Each component
has collection of test groups, which has a collection of test cases, each of
which contains a sequence of steps.

```{toctree}
:titlesonly: true

directories
components
test_groups
test_cases
steps
suites
```
