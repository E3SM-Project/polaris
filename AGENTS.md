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
