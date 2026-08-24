---
applyTo: "utils/benchmark/**"
---

# Benchmark Workflow Instructions

These rules are specific to the benchmarking driver in
`utils/benchmark`.  Repository-wide rules in `AGENTS.md` still apply.

## Running a benchmark

- Always run with `--dry-run` first and show the resolved commit hashes
  and planned commands to the user before running for real.
- Prefer editing a copy of `example.cfg` or using the command-line
  overrides.  Do not hard-code paths in the driver modules.
- Do not add `--model`, `--branch`, `-p`, `-w`, `-b`, `-f`, `--build` or
  `--clean_build` to `setup_command`; the driver appends them.
- Do add `--suite_name` to a `polaris setup` command; the driver requires
  it so that the benchmark is not named `custom`.
- When only polaris differs between the two sides, suggest
  `component_path` so that the model is built once and shared rather than
  built twice.  Neither `--rebuild` nor `--clean-build` is needed for a
  first build, and `--clean-build` is refused with a `component_path`.

## Adopted worktrees

- When a side uses `source = existing`, never run `git fetch`,
  `checkout`, `submodule update`, `reset`, `clean`, `rm` or any other
  mutating command against the adopted worktree yourself.  Polaris' own
  build does write into it when one is requested, so do not tell the user
  the worktree is left untouched unless nothing is being built.
- If an adopted worktree is dirty or is missing an initialized
  submodule, stop and ask the user to resolve it.  Do not pass
  `--allow-dirty` without the user explicitly asking for it.  Report what
  actually made it dirty: a submodule built in place does not count, so
  the cause is polaris-level changes, edited tracked source in the
  submodule the model is built from, or a submodule at a commit other
  than the pinned one.
- A task that runs no model needs `model = none`, not an initialized
  submodule.  Check that before asking the user to clone one.

## Guardrails

- Do not weaken or bypass the guardrails in `_check_guardrails` or
  `gitrepo.adopt` to make a run succeed.
- `--allow-multiple-changes`, `--allow-env-mismatch` and `--allow-dirty`
  each make results harder to interpret.  Only pass them when the user
  has asked for it, and say so in the summary.

## Environment

- The load script must already exist in the worktree.  If it does not,
  stop and tell the user to run `./deploy.py` themselves, per
  `AGENTS.md`.  Never run `./deploy.py`.

## Stop conditions

- On a build or run failure, collect the log path, report it, and stop.
  Do not retry with different flags unless the user asks.
