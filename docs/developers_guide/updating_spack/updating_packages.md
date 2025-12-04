# Updating Spack Dependencies

Updating Spack dependencies in Polaris is a key part of maintaining
compatibility with E3SM components and ensuring that all required system
libraries and tools are available for developers. Unlike Conda dependencies,
which are managed per-developer and updated more frequently, Spack environments
are shared among developers on supported machines and are updated less often
due to the time and coordination required. When Spack dependencies change—such
as when new versions of libraries like ESMF, MOAB, or SCORPIO are needed, or
when system modules are updated—a new version of the shared Spack environment
must be built and deployed across all supported platforms. This process also
typically involves incrementing the Polaris version (usually the minor version)
to track the change. The following workflow outlines the steps required to
update Spack dependencies in Polaris.

## 🚩 Workflow for Updating Spack Dependencies

1. **Create a Branch**
   Start by creating a branch named `update-to-<version>`, where `<version>`
   is the new Polaris version you are preparing (e.g.,
   `update-to-0.9.0-alpha.1`).

2. **Bump the Polaris Version**
   Update the version number in `polaris/version.py` to the new version.
   Typically, when updating Spack dependencies, increment the *minor* version,
   reset the *patch* version to `0`, and set the *alpha* version to `1`.
   For example, if the current version is:
   ```python
   __version__ = '0.8.0-alpha.3'
   ```
   change it to:
   ```python
   __version__ = '0.9.0-alpha.1'
   ```
   Commit this change with a message like "Update Polaris to v0.9.0-alpha.1".

3. **Update Spack Dependency Versions**
   Edit `deploy/default.cfg` to update the versions of Spack dependencies as
   needed. The relevant sections are:
   ```cfg
   # versions of conda or spack packages (depending on machine type)
   esmf = 8.8.1
   metis = 5.1.0
   netcdf_c = 4.9.2
   netcdf_fortran = 4.6.2
   pnetcdf = 1.14.0

   # versions of spack packages
   albany = developcompass-2024-03-13
   # cmake newer than 3.23.0 needed for Trilinos
   cmake = 3.23.0:
   hdf5 = 1.14.6
   lapack = 3.9.1
   spack_moab = master
   parmetis = 4.0.3
   petsc = 3.19.1
   scorpio = 1.7.0
   ```

4. **Commit and Make a PR**
   Commit your changes and make a pull request to the Polaris repo.  This
   will be used to keep track of the updated packages as well as the testing
   and deployment process. You can use
   [this example](https://github.com/E3SM-Project/polaris/pull/319)
   as a template.  Make sure to include:
   * An **Updates:** section describing the packages (both Conda and Spack)
     that are updated as well as a description of what the new version
     provides or why it is needed.  For example:

     ``` markdown
     ## Updates:
     - esmf v8.8.1
     - hdf5 v1.14.6
     - mache v1.31.0 -- brings in Aurora support and some related reorganization and clean-up
     - moab master -- brings in bug fix related to remapping from cubed-sphere grids to MPAS meshes
     - mpas_tools v1.1.0 -- brings in bug fix to barotropic streamfunciton
     - parallelio v2.6.6
     - pnetcdf v1.14.0
     - scorpio v1.7.0
     ```

   * A **Testing:** section with a checklist for each machine, compiler and
     MPI variant that will be tested.  This can also be a helpful place to
     coordinate who will test what (if multiple maintainers are involved) and
     to note any issues you are seeing (pointing to a new or existing issue
     under [https://github.com/E3SM-Project/polaris/issues](https://github.com/E3SM-Project/polaris/issues)).  For example:

     ``` markdown
     ## Testing

     MPAS-Ocean with `pr`:
     - [ ] chrysalis (@xylar)
       - [ ] intel and openmpi
       - [ ] gnu and openmpi
     - [ ] frontier (@xylar)
       - [ ] craygnu and mpich
       - [ ] craycray and mpich
     - [ ] pm-cpu (@xylar)
       - [ ] gnu and mpich
       - [ ] intel and mpich - still seeing https://github.com/E3SM-Project/polaris/issues/205

     Omega CTests:
     - [ ] chrysalis (@xylar)
       - [ ] intel
       - [ ] gnu
     - [ ] frontier (@xylar)
       - [ ] craygnu
       - [ ] craygnu-mphipcc
       - [ ] craycray
       - [ ] craycray-mphipcc
       - [ ] crayamd
       - [ ] crayamd-mphipcc
     - [ ] pm-cpu (@xylar)
       - [ ] gnu
       - [ ] intel
     - [ ] pm-gpu (@xylar)
       - [ ] gnugpu
     ```

   * A **Deployment:** section with another checklist for each machine,
     compiler and MPI variant on all supported machines.  Again, it will be
     helpful to note who will do the deployemnt (and final testing) and any
     issues that persist:

     ``` markdown
     ## Deploying

     MPAS-Ocean with `pr`:
     - [ ] chrysalis (@xylar)
       - [ ] intel and openmpi
       - [ ] gnu and openmpi
     - [ ] frontier (@xylar)
       - [ ] craygnu and mpich
       - [ ] craycray and mpich
     - [ ] pm-cpu (@xylar)
       - [ ] gnu and mpich
       - [ ] intel and mpich  - still seeing https://github.com/E3SM-Project/polaris/issues/205

     Omega CTests:
     - [ ] chrysalis (@xylar)
       - [ ] intel
       - [ ] gnu
     - [ ] frontier (@xylar)
       - [ ] craygnu
       - [ ] craygnu-mphipcc
       - [ ] craycray
       - [ ] craycray-mphipcc
       - [ ] crayamd
       - [ ] crayamd-mphipcc
     - [ ] pm-cpu (@xylar)
       - [ ] gnu
       - [ ] intel
     - [ ] pm-gpu (@xylar)
       - [ ] gnugpu
     ```
---

## ➕ Adding a New Spack Package

To add a new Spack package to the Polaris deployment, follow these steps:

1. **Add the Package Version to `default.cfg`**

   In the `[deploy]` section of `deploy/default.cfg`, add a new entry for your
   package with the desired version. For example:
   ```ini
   # versions of spack packages
   mypackage = 1.2.3
   ```

2. **Edit `bootstrap.py` to Add the Package to the Spack Specs**

   In `deploy/bootstrap.py`, you must:
   - Read the version from the config, following the pattern used for other
     packages:
     ```python
     mypackage = config.get('deploy', 'mypackage')
     ```
   - Add the package to the list of Spack specs, following the approach used
     for existing dependencies such as `esmf`, `metis`, `parmetis`, or
     `scorpio`. For example:
     ```python
     if mypackage != 'None':
         specs.append(f'mypackage@{mypackage}+mpi+shared')
     ```
     Adjust the variant flags (`+mpi`, `+shared`, etc.) as appropriate for
     your package.

   **Examples from existing packages:**
   ```python
   esmf = config.get('deploy', 'esmf')
   metis = config.get('deploy', 'metis')
   parmetis = config.get('deploy', 'parmetis')
   scorpio = config.get('deploy', 'scorpio')

   ...

   if esmf != 'None':
       specs.append(f'esmf@{esmf}+mpi+netcdf~pnetcdf~external-parallelio')
   if metis != 'None':
       specs.append(f'metis@{metis}+int64+real64~shared')
   if parmetis != 'None':
       specs.append(f'parmetis@{parmetis}+int64~shared')
   if scorpio != 'None':
       specs.append(
           f'e3sm-scorpio@{scorpio}+mpi~timing~internal-timing~tools+malloc'
       )
   ```

3. **Follow the Process for Existing Spack Dependencies**

   Review how other Spack dependencies are handled in both `default.cfg` and
  `bootstrap.py` to ensure consistency. This includes:
   - Reading the version from the config.
   - Adding the correct Spack spec string to the `specs` list.
   - Handling any special environment variables or linking flags if needed.

4. **Test and Document**

   - Test the new package (as part of test deployments of Polaris) on all
     supported machines and compilers.
   - Document the addition in your PR, including the version.

**Tips:**
- If your package requires special variants or dependencies, consult the Spack
  documentation for the correct spec syntax.
- If the package is only needed on certain machines or for certain workflows,
  consider making its inclusion conditional. For examples of this process,
  see how the `--with_albany` and `--with_petsc` flags (defined in
  `deploy/shared.py`) are used to include the `albany` and `petsc` packages,
  respectively, in specialized Spack environments that include these libraries.

---

## 📝 Summary

- Create a branch for the update.
- Bump the Polaris version (minor version up, patch to 0, alpha to 1).
- Update Spack dependency versions in `deploy/default.cfg`.
- Commit, test, and deploy on all supported machines.
- Be aware of special handling for MOAB and SCORPIO.

If you need to update Conda dependencies as well, see
[Updating Conda Dependencies](../updating_conda.md).

