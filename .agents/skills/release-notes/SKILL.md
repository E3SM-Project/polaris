---
name: release-notes
description: Write or revise the notes for a Polaris GitHub release. Use when preparing a release or rewriting an existing release's description.
---

# Release notes

The reader uses Polaris and wants to know what is new and what will break
when they upgrade. The notes replace GitHub's generated list of pull
requests, but every pull request still appears somewhere.

## Structure

```
<2 or 3 sentences: what this release is about>

## Major features
### <Theme>
<2 to 4 sentences.> (#N, #M, @author, @author)

## Minor features
### Ocean tasks
### Ocean framework
### Mesh and `e3sm/init`
### Framework
- <What changed> (#N, @author)

## Breaking changes
## Bug fixes
## Documentation
## Developer tools and CI
## Dependencies
## New contributors
**Full changelog**: https://github.com/E3SM-Project/polaris/compare/<prev>...<tag>
```

Drop an empty section or subsection. Add a subsection under Minor features
when a new area needs one.

## Gathering

- Take the list of pull requests from GitHub, not from merge commits, which
  miss squash merges:
  `gh api repos/E3SM-Project/polaris/releases/generate-notes -f tag_name=<tag> -f previous_tag_name=<prev> -q .body`.
  Keep its New contributors list.
- Read each pull request's title, labels and description with
  `gh pr view`.
- Take dependency versions from `deploy/pins.cfg`, `deploy/pixi.toml.j2`
  and `pyproject.toml` at the two tags, not from titles. Many bumps arrive
  in feature pull requests; find them with
  `git log --first-parent <prev>..<tag> -- deploy/pins.cfg`.
- Find renamed or removed tasks with `git diff <prev> <tag> -- polaris/suites`.

## Sorting

- A major feature is a theme that spans several pull requests or a
  capability someone would go looking for. The line is blurry; do not
  agonize over it.
- Breaking changes: renamed task paths, meshes or compilers; removed
  modules, functions or config options; anything a user's scripts or
  configs will trip over. A pull request can appear both here and in a
  feature or fix section.
- Bug fixes say what was wrong, not how it was fixed. Flag a fix that
  changes answers.
- Dependencies collapse the Omega and E3SM submodule updates into one line
  each, and the bot updates of GitHub Actions and pre-commit hooks into
  another.
- Leave out alpha version bumps unless they changed a pin, in which case
  they go under Dependencies with that pin.

## Writing

- One line per bullet and per paragraph; GitHub release notes are not
  hard-wrapped.
- Rewrite titles as what changed for the user, not what the pull request
  did.
- Credit the human: a pull request opened by Copilot or Claude for @xylar
  is `@xylar`.
- End with the signature from `AGENTS.md`.

## Checking

Every number from the generated notes must appear in the draft, apart from
the alpha bumps you dropped on purpose:

```
gh api repos/E3SM-Project/polaris/releases/generate-notes \
    -f tag_name=<tag> -f previous_tag_name=<prev> -q .body \
  | grep -o 'pull/[0-9]*' | cut -d/ -f2 | sort -nu \
  | while read n; do grep -q "#$n\b" notes.md || echo "missing #$n"; done
```

Show the draft to the user before posting it with
`gh release edit <tag> --notes-file notes.md`.

## Example

From the 1.1.0 notes:

> ### Tasks and suites across components
> Each component now sets up the steps it owns, so a task or suite can
> include shared steps from another component with that component's config
> options. Helpers called by several tasks can now share one config, and
> the Coriolis helpers move into the framework so any component can use
> them. (#704, #686, #692, @xylar)

> ## Breaking changes
> - The unified meshes use dashes rather than dots, e.g. `u-oi30-lr10`, so
>   they can be E3SM grid aliases (#798)

> ## Bug fixes
> - Make the `sphere_transport`, `geostrophic` and `merry_go_round` viz
>   steps work for both models; filament diagnostics now use the configured
>   time, which changes their values (#767, @xylar)

The full 1.0.0 and 1.1.0 notes are the reference for tone and length.
