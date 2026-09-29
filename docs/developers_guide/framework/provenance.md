(dev-provenance)=

# Provenance

The `polaris.provenance` module defines a function
{py:func}`polaris.provenance.write()` for creating a file in the base work
directory with provenance, such as the git version, conda packages, polaris
commands, and tasks.

For both Polaris and the component, the file records the git version, the
full hash and the last five first-parent commits (`polaris git version`,
`polaris git hash`, `polaris git log` and the same for `component`).  The logs
are on indented lines after their label, so every other entry can be read one
line at a time.

The component entries come from the source record that Polaris's build scripts
write into the build directory (see {ref}`dev-build`), so they name the commit
that was built.  For a build without a record, such as one made by hand, they
come from the build's source tree at setup, which may have moved since the
build, and are marked `(at setup, not build)`.

{py:func}`polaris.provenance.read()` reads the file back, returning the
entries before the list of tasks and the git entries for Polaris and the
component, with their logs and whether they were marked
`(at setup, not build)`.  The file also records the `model` the component
is, `omega` or `mpas-ocean`, when there is one.
