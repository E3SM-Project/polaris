(ocean-suites)=

# Suites

The ocean component includes a number of {ref}`suites` that can be used to
run a series of ocean tasks and optionally compare them against a baseline
run of the same tasks.  To set them up, run:

```bash
polaris suite -c ocean -t <suite_name> ...
```

Below are details on some of the most commonly used suites.  The other suites
are mostly focused on specific tests as indicated by their names.

(ocean-suite-pr)=

## pr suite

The `pr` suite is designed for testing pull-requests (PRs) that involve
changes to the Ocean component or the Polaris framework.  It includes some
basic tests that are always expected to work, and which should indicate if
any changes have been inadvertently introduced by the PR.  For now, the
suite is designed for use with MPAS-Ocean but not fully supported by Omega.

```none
ocean/planar/baroclinic_channel/10km/threads
ocean/planar/baroclinic_channel/10km/decomp
ocean/planar/baroclinic_channel/10km/restart
ocean/planar/barotropic_channel/default
ocean/planar/ice_shelf_2d/5km/z-star/default/with_restart
ocean/planar/ice_shelf_2d/5km/z-level/default/with_restart
ocean/planar/inertial_gravity_wave/convergence_both
ocean/planar/internal_wave/standard/default
ocean/planar/internal_wave/vlr/default
# currently not converging in MPAS-Ocean
# ocean/planar/manufactured_solution/convergence_both
ocean/planar/merry_go_round/default
ocean/planar/overflow/linear/zstar/smoke_test_horiz_adv_order_2
ocean/planar/overflow/linear/zstar/smoke_test_horiz_adv_order_3
ocean/planar/overflow/linear/zstar/smoke_test_horiz_adv_order_4
ocean/planar/overflow/nonlinear/pstar/smoke_test_horiz_adv_order_4_del4
ocean/single_column/cvmix
ocean/single_column/ekman
ocean/single_column/ideal_age
ocean/single_column/inertial
ocean/spherical/icos/cosine_bell/decomp
ocean/spherical/icos/cosine_bell/restart
```

(ocean-suite-nightly)=

# nightly suite

The `nightly` suite is similar to the `pr` suite but is designed to allow for
slightly heavier testing on a nightly basis.  For now, the suite actually
includes fewer tests than `pr` but it is expected to be fleshed out as Omega
development matures:

```none
ocean/planar/baroclinic_channel/10km/threads
ocean/planar/baroclinic_channel/10km/decomp
ocean/planar/baroclinic_channel/10km/restart
ocean/planar/ice_shelf_2d/5km/z-star/default/with_restart
ocean/planar/ice_shelf_2d/5km/z-level/default/with_restart
ocean/planar/inertial_gravity_wave/convergence_both
# ocean/planar/manufactured_solution
ocean/spherical/icos/cosine_bell/decomp
ocean/spherical/icos/cosine_bell/restart
```

# omega_pr suite

The `omega_pr` suite is designed to test changes in Omega or the affects of
Polaris changes on Omega results.

Here are the tests in the suite:
```none
ocean/column/horiz_press_grad/salinity_gradient
ocean/planar/baroclinic_channel/10km/default
ocean/planar/barotropic_gyre/munk/free-slip
ocean/planar/manufactured_solution/convergence_both/default
ocean/planar/manufactured_solution/convergence_both/del2
ocean/planar/manufactured_solution/convergence_both/del4
ocean/planar/merry_go_round/default
ocean/planar/overflow/linear/zstar/smoke_test_horiz_adv_order_2_del4
ocean/planar/overflow/linear/zstar/smoke_test_horiz_adv_order_3
ocean/planar/overflow/linear/zstar/smoke_test_horiz_adv_order_4
ocean/planar/overflow/nonlinear/pstar/smoke_test_horiz_adv_order_4_del4
ocean/spherical/icos/cosine_bell/decomp
ocean/spherical/icos/cosine_bell/restart
```

(ocean-suite-omega-analysis)=

## omega_analysis suite

The `omega_analysis` suite analyzes a simulation that has already been run,
rather than running one.  It is pointed at a completed Omega simulation
through a config file and produces plots and the netCDF data behind them.  See
{ref}`ocean-analysis` for the config file it needs and for what each task
produces.

Unlike the other suites here, it needs neither an Omega nor an MPAS-Ocean
build, since no model is run, and it can be run on the machine where the
simulation output lives without copying that output.  Because there is no
build to detect the model from, `--model omega` is required and no
`-p`/`--component_path` is given:

```bash
polaris suite -c ocean -t omega_analysis -w <work_dir> -f analysis.cfg \
    --model omega
```

The tasks in the suite are:

```none
ocean/analysis/climatology_maps
ocean/analysis/heat_content_series
ocean/analysis/global_stats
ocean/analysis/moc
```

(ocean-suite-framework-pr)=

## framework_pr suite

The `framework_pr` suite is designed for testing pull-requests (PRs) that
involve changes to the Polaris and/or Ocean framework.  It includes the tests
in the `pr` suite plus additional tests focued on visualizaiton and remapping.
The tasks in this suite include:

```none
## pr suite
ocean/planar/baroclinic_channel/10km/threads
ocean/planar/baroclinic_channel/10km/decomp
ocean/planar/baroclinic_channel/10km/restart
ocean/planar/ice_shelf_2d/5km/z-star/default/with_restart
ocean/planar/ice_shelf_2d/5km/z-level/default/with_restart
ocean/planar/inertial_gravity_wave/convergence_both
ocean/planar/internal_wave/standard/default
ocean/planar/internal_wave/vlr/default
# ocean/planar/manufactured_solution/convergence_both
ocean/single_column/cvmix
ocean/single_column/ideal_age
ocean/spherical/icos/cosine_bell/decomp
ocean/spherical/icos/cosine_bell/restart

## viz
ocean/planar/baroclinic_channel/10km/default
ocean/planar/ice_shelf_2d/5km/z-star/default/with_viz
ocean/spherical/icos/rotation_2d/with_viz

## remapping
ocean/planar/isomip_plus/4km/z-star/ocean0
```

(ocean-suite-convergence)=

## convergence suite

The `convergence` suite is designed for running all convergence tests. To
speed up the process, most tests have cached base meshes. Here are the tests
included:

```none
ocean/planar/inertial_gravity_wave/convergence_both
ocean/planar/manufactured_solution/convergence_both/default
ocean/planar/manufactured_solution/convergence_both/del2
ocean/planar/manufactured_solution/convergence_both/del4
ocean/spherical/icos/correlated_tracers_2d
ocean/spherical/qu/correlated_tracers_2d
ocean/spherical/icos/cosine_bell/convergence_both
ocean/spherical/qu/cosine_bell/convergence_both
ocean/spherical/icos/geostrophic/convergence_both
ocean/spherical/qu/geostrophic/convergence_both
ocean/spherical/icos/divergent_2d
ocean/spherical/qu/divergent_2d
ocean/spherical/icos/nondivergent_2d
ocean/spherical/qu/nondivergent_2d
ocean/spherical/icos/rotation_2d
ocean/spherical/qu/rotation_2d
```
