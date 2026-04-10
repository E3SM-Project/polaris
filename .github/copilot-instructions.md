# Polaris Copilot Instructions

Follow the repository's automated style configuration in
`pyproject.toml` and `.pre-commit-config.yaml`.

- Keep changes consistent with existing Polaris patterns.
- Treat `deploy.py` and `deploy/cli_spec.json` as contract files shared
  with the `mache` package.
- Do not modify `deploy.py` or `deploy/cli_spec.json` directly in
  Polaris.
- If a change appears necessary, stop and note that the change must be
  made in `mache` first, then synced back into Polaris using the normal
  upstream update process.
- For Python, follow the path-specific instructions in
  `.github/instructions/python.instructions.md`.
- For documentation in `docs/`, follow the path-specific instructions in
  `.github/instructions/docs.instructions.md`.
- Run pre-commit on changed files is required before finishing; if sandboxed
  execution fails, request escalation and do not close the task until it has
  run or the user declines.
- Prefer changes that pass the configured pre-commit hooks without
  adding ignores or suppressions.
