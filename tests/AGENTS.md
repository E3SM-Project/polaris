# Unit test instructions

These apply to everything under `tests/`, on top of the repository's
`AGENTS.md`.

## Do not assert configured values

- Never assert that an option shipped with Polaris has a particular
  value. That covers options in the package's `.cfg` files, yaml model
  configs and dynamic-adjustment schedules, and anything built directly
  from them: a `ForwardStage` field, a namelist or yaml option, a step's
  resources.
- This includes tables of expected per-mesh settings and "the default is
  X" tests.
- Such a test compares two copies of the same value. It catches no bug,
  and it fails every time someone retunes the option, so the value has to
  be changed in two places.
- An option that must have one particular value should not be an option.
  Make it a constant in the code instead.
- Existing tests that do this are not a precedent. Do not add more, and
  remove any you find.

## What you may check

- A flag, or a choice among a few settings, where the other setting would
  be wrong rather than just different. For example, a config for
  comparing with Omega must turn off physics Omega does not have, and a
  wind-forced run must read its forcing stream. Say in the test why the
  other setting is wrong.
- A number within a range, or in relation to another value, for example
  a threshold that has to stay well below an observed floor. Never a
  single number.
- Structure: a section or option exists and parses, a per-mesh file names
  a real mesh, a stream contains a field that something downstream reads.

## What to test instead

- Test what the code does with a value, using a value the test chooses:
  write a small config or call `config.set()`, then check that the code
  reads, overrides, scales or passes on that value.
- To check that one config layer overrides another, compare the result
  with the layer's own file, not with a copy of its contents.
- When a test needs a shipped value as an input, read it from the config
  instead of repeating it.
