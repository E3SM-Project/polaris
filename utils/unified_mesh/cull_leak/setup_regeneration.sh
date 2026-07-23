#!/bin/bash
# Set up the regeneration runs that validate the cull-leak fix on all
# four unified meshes (see PLAN_fix_unified_mesh_cull_leak.md and the
# unified_mesh_cull_leak design doc).
#
# Prerequisites (developer actions):
#   - ./deploy.py has been run on this branch so pixi-env/ exists
#   - a compiled model build (Omega or MPAS-Ocean) to point -p at
#
# What re-runs vs what stays cached: only the shared coastline
# compute/remap steps are cached by default, and they are unaffected by
# the fix, so their caches remain valid.  The sizing-field, base-mesh
# and all e3sm/init topography steps run fresh, which is exactly what
# the fix changes.  The new dcEdge diagnostic runs in each mesh's
# topo/cull mask step and will fail the run if resolution still leaks
# into the ocean/sea-ice domain.
#
# Usage:
#   ./setup_regeneration.sh <work_dir> <build_dir> [<model>]
#
# Review the generated job script in <work_dir> before submitting.

set -e

if [ $# -lt 2 ]; then
    echo "Usage: $0 <work_dir> <build_dir> [<model>]"
    exit 1
fi

work_dir=$1
build_dir=$2
model=${3:-omega}

tasks=(
    ocean/spherical/realistic_global/u.oi30.lr10/init/task
    ocean/spherical/realistic_global/u.oi240.lr240/init/task
    ocean/spherical/realistic_global/u.oi6to18.lr6to10/init/task
    ocean/spherical/realistic_global/u.oi.so12to30.lr10/init/task
    ocean/spherical/realistic_global/u.oi30.lr10/forward/task
    ocean/spherical/realistic_global/u.oi240.lr240/forward/task
    ocean/spherical/realistic_global/u.oi6to18.lr6to10/forward/task
    ocean/spherical/realistic_global/u.oi.so12to30.lr10/forward/task
)

polaris setup \
    -t "${tasks[@]}" \
    --model "${model}" \
    -w "${work_dir}" \
    -p "${build_dir}"

echo
echo "Setup complete.  Review the job script in ${work_dir} before"
echo "submitting.  After the run, check that the topo/cull mask steps"
echo "passed the dcEdge diagnostic for all four meshes and spot-check"
echo "the former hotspots (Banc d'Arguin, Chukotka lagoons, Foxe"
echo "Basin) with utils/unified_mesh/cull_leak/diagnose_dc_edge.py."
