# Updating the E3SM Spack Fork for Polaris

Polaris relies on a custom fork of Spack (the E3SM fork) to build
performance-critical software components that are not managed by Conda.
This fork includes specialized packages (e.g., `moab`, `e3sm-scorpio`, `esmf`)
and system-aware configurations to support a wide range of HPC environments.

This page outlines the steps for updating and managing the E3SM Spack fork
during a Polaris release cycle.

---

## Repo Location

The E3SM Spack fork lives at:
🔗 [https://github.com/E3SM-Project/spack](https://github.com/E3SM-Project/spack)

---

## Key Tasks

### 1. Add or Update Package Versions

You may need to:

* Add new versions of packages like `moab`, `esmf`, etc.
* Update build configurations, variants, or patches
* Rebase onto new releases of the main
  [spack repo](https://github.com/spack/spack)

Follow Spack’s standard packaging conventions. Builds will typically be tested
as part of Polaris deployment, so no other testing is typically necessary or
practical.

After changes are validated, push them to the appropriate branch or branches
(see next section).

---

### 2. Create `spack_for_mache_<version>` Branches

The main development branch on E3SM's spack fork is `develop`.  Each release of
`mache` also references a specific Spack branch named:

```
spack_for_mache_<version>
```

Example:

```
spack_for_mache_1.32.0
```

To create one from a local clone of the E3SM spack repo:

```bash
git checkout develop
git checkout -b spack_for_mache_1.32.0
git push origin spack_for_mache_1.32.0
```
This ensures that the version of `mache` used for deployment has a stable and
reproducible Spack reference.  During development of a `mache` version, this
also lets you make potentially breaking changes to `spack_for_mache_<version>`
for testing without breaking the `develop` branch.

Once you have a relatively stable `spack_for_mache_<version>` branch, you can
push the changes you have made to `develop` so they are available for future
`mache` versions and other users of E3SM's spack fork.

```bash
git checkout develop
git reset --hard spack_for_mache_1.32.0
git push origin develop
```
Please be careful not to use `git push --force` here.  You should only be
adding new commits, not changing the history of `develop`.

### 3. Rebasing `develop` onto Spack Releases

One important maintenance task for the E3SM Spack fork is to keep it up-to-date
with the [main Spack repo](https://github.com/spack/spack).  This requires
interactively rebasing the `develop` branch onto the release, interactively
selecting only commits authored within the E3SM Spack fork (i.e., excluding
upstream Spack commits), and troubleshooting any merge conflicts that arise.

Coordinate with other users of the fork before force-pushing.

---

## Best Practices

* Keep `develop` clean and stable — avoid experimental changes
* Use branches to track specific `mache` releases
* Coordinate with other package maintainers when rebasing the `develop`
  branch or updating shared packages

---

➡ Next: [Updating `mache`](updating_mache.md)
