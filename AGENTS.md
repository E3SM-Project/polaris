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

## GitHub pull requests and issues

- Do not hard-wrap. Write each paragraph and each bullet as a single
  line, however long. GitHub wraps them for display, and hard breaks
  make later edits show up as reflowed paragraphs in the diff.
- Start with a paragraph summarizing what the pull request or issue is
  about, then use sections for the detail.
- Keep the description in a file at the root of the worktree for the
  branch it describes, and never commit it. It is a draft to paste into
  GitHub, not part of the branch's content.
- Follow `.github/pull_request_template.md`: the description goes at
  the top, keep only the checklist lines that apply, and use closing
  keywords for any issue the pull request fixes.
- Do not list individual commits in a pull request description. The
  commits are already on the pull request; describe what the change
  accomplishes as a whole instead.
- Do not describe testing in a pull request description. Testing goes
  in its own `Testing` comment on the pull request, which is what the
  template's checklist asks for.
- An issue should say what happens, what was expected instead, and
  enough about the configuration and commands used to reproduce it.

## Writing for human readers

These rules apply to anything a colleague reads: GitHub comments, pull
request descriptions, issues, plans, design notes. Not code comments or
commit messages, where a reader who wants the mechanism is already in the
right place. Per-artifact rules and worked examples are in
`.claude/skills/<artifact>/SKILL.md`, as plain markdown. Claude Code loads
the matching one automatically; other agents should read it before writing.

Write less; do not pack the same content into denser sentences. Keep
headings, tables and links. Colleagues mostly write unstructured prose, and
structure is an improvement on it. The problem is length.

- **Lead with the answer.** The first two sentences say what you found,
  changed, or propose. Setup and reproduction go last.
- **One point per paragraph, and few paragraphs.** Colleagues write one to
  three per comment; recent AI-written ones ran to eighteen. That gap is
  the complaint. Say each thing once.
- **Do not narrate the mechanism.** The chain of calls, and why the fix is
  right, go in the commit message. Here, say what broke and where to look.
- **Cut clauses that qualify rather than inform**, and any sentence whose
  only job is to justify the one before it. One clause per sentence where
  one will do.
- **Use backticks about half as often as feels natural.** They are for what
  a reader would type or grep. Code blocks hold artifacts you did not
  write, never authored prose.
- **One document, one decision.** Anything still relevant after this merges
  is an issue, not a comment.

Sign anything posted to GitHub on someone's behalf:

```
---

*Posted by <agent> on @<user>'s behalf. The testing, analysis and wording
above are AI-authored; please check them accordingly.*
```

Name the agent, not the vendor: `Claude Code`, `Codex`, and so on.

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
