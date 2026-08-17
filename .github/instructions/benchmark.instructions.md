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

## Adopted worktrees

- When a side uses `source = existing`, the adopted worktree is
  read-only.  Never run `git fetch`, `checkout`, `submodule update`,
  `reset`, `clean`, `rm` or any other mutating command against it.
- If an adopted worktree is dirty or is missing an initialized
  submodule, stop and ask the user to resolve it.  Do not pass
  `--allow-dirty` without the user explicitly asking for it.

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
