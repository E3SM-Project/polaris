(mesh-base-mesh-task)=

# Base Mesh Tasks

The `mesh/spherical/qu/base_mesh/XXXkm/task` and
`mesh/spherical/icos/base_mesh/XXXkm/task` tasks can be used to create
spherical, uniform MPAS meshes at the given resolution that are either
quasi-uniform (`qu`) or subdivided icosahedral (`icos`).

There are also two variable resolution base meshes: `rrs6to18km` and
`so12to30km`.

The RRS mesh has a resolution that ranges from 6 km at the
poles to 18 km at the equator, approximately scaling with the Rossby radius.

```{image} ../../../developers_guide/mesh/framework/images/rrs.png
:align: center
:width: 500 px
```

The SO mesh has a quasi-uniform, 30 km background resolution that transitions
to 12 km in region surrounding the Southern Ocean.  The boundary of high
resolution region attempts to approximatly follow dynamical contours in
the ocean, since rapid changes in resolution have been shown to steer ocean
currents along isocontours of resolution.

```{image} ../../../developers_guide/mesh/framework/images/so.png
:align: center
:width: 500 px
```