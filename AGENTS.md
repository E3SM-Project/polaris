# Polaris Agent Instructions

These instructions apply to the whole repository unless a deeper
`AGENTS.md` overrides them.

## Source of truth

- Follow the repo's automated style and lint configuration in
  `pyproject.toml` and `.pre-commit-config.yaml`.
- If an instruction here conflicts with automated tooling, follow the
  automated tooling.

## Environment

- If `pixi-env/` exists, it is the preferred development environment for
  Python, testing, linting, and `pre-commit`. It is created by
  `./deploy.py`.
- AI agents should not run `./deploy.py` to create `pixi-env/`
  themselves. Creating or refreshing `pixi-env/` is a developer action.
- Prefer running tools from `pixi-env/.pixi/envs/default/bin/` (for
  example `python`, `pytest`, `pre-commit`, `ruff`, and `mypy`) instead
  of relying on the system environment.
- Only fall back to other Python environments if `pixi-env/` does not
  exist or is clearly incomplete.

## Python style

- Keep Python lines at 79 characters or fewer whenever possible.
- Use `ruff format` style. Do not preserve manual formatting that Ruff
  would rewrite.
- Keep imports at module scope whenever possible. Avoid local imports
  unless they are needed to prevent circular imports, defer expensive
  dependencies, or avoid optional dependency failures.
- Avoid nested functions whenever possible. Prefer private module-level
  helpers instead.
- Put public functions before private helper functions whenever
  practical.
- Name private helper functions with a leading underscore when that fits
  existing repo conventions.

## Documentation

- When writing documentation for component tasks, follow the relevant
  `template.md` format and its inline instructions whenever a component
  task template is available.
- Prefer starting from the existing template instead of creating task
  documentation pages from scratch.

## Supported machines

- `docs/developers_guide/supported_machines.yaml` is the source of the
  supported machine table in the Developer's Guide. Update it whenever
  machines are added or removed, or compilers and MPI libraries are
  added, removed, or renamed.
- Keep it consistent with the machine config files in
  `polaris/machines/`: the `mpi_<compiler>` options under `[deploy]`
  define the valid compiler and MPI combinations, and the
  `<compiler>_<mpi>_target` options under `[build]` define the
  `mpas_target` values (use `null` for Omega-only combinations).
- When a compiler is added or renamed, update every place it appears:
  the machine config file in `polaris/machines/`,
  `supported_machines.yaml`, the machine pages in both the User's and
  Developer's Guides, and any `load_polaris_*.sh` examples in the
  documentation and tutorials.

## Contracts

- Treat `deploy.py` and `deploy/cli_spec.json` as contract files shared
  with the `mache` package.
- Do not modify `deploy.py` or `deploy/cli_spec.json` directly in
  Polaris.
- If a change appears necessary, stop and note that the change must be
  made in `mache` first, then synced back into Polaris using the normal
  upstream update process.

## Validation

- Run pre-commit on changed files is required before finishing; if sandboxed
  execution fails, request escalation and do not close the task until it has
  run or the user declines.
- Prefer fixing lint and formatting issues rather than suppressing them.
