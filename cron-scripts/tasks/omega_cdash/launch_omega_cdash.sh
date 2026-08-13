#!/usr/bin/env bash
set -eo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_NAME="$(basename "${BASH_SOURCE[0]}")"
echo "[$(date)] Starting $SCRIPT_NAME"

export OMEGA_CDASH_BASEDIR="${CRONJOB_BASEDIR:?CRONJOB_BASEDIR must be set}/tasks/omega_cdash"
export TESTROOT="${OMEGA_CDASH_BASEDIR}/tests"
mkdir -p "$OMEGA_CDASH_BASEDIR"
mkdir -p "$TESTROOT"


# Configuration
export OMEGA_ROOT="${OMEGA_CDASH_BASEDIR}/Omega"
REMOTE_URL="https://github.com/E3SM-Project/Omega.git"
BRANCH="develop"

# 1. & 2. Check existence and handle repository state
if [ ! -d "$OMEGA_ROOT/.git" ]; then
    echo "Repository not found. Cloning..."
    git clone -b "$BRANCH" "$REMOTE_URL" "$OMEGA_ROOT"
    cd "$OMEGA_ROOT" || exit
else
    echo "Repository exists. Updating to latest remote state..."
    cd "$OMEGA_ROOT" || exit

    # Ensure we are on the correct branch and sync with origin
    git fetch origin
    git checkout "$BRANCH"
    git reset --hard "origin/$BRANCH"
fi

# 3. Update specific submodules recursively
echo "Updating submodules..."
git submodule update --init --recursive externals/ekat externals/scorpio cime components/omega/external

wget -O ${TESTROOT}/OmegaMesh.nc https://web.lcrc.anl.gov/public/e3sm/polaris/ocean/omega_ctest/ocean.QU.240km.omega_vars.260807.nc
wget -O ${TESTROOT}/OmegaSphereMesh.nc https://web.lcrc.anl.gov/public/e3sm/polaris/ocean/omega_ctest/cosine_bell_icos480.omega_vars.260807.nc
wget -O ${TESTROOT}/OmegaPlanarMesh.nc https://web.lcrc.anl.gov/public/e3sm/polaris/ocean/omega_ctest/PlanarPeriodic48x48.omega_vars.260720.nc

export RUNSCRIPT_DIR="${HERE}"
export CRONJOB_MACHINE
export COMPILER_MAP_DEF
export CRONJOB_DATE
export TESTROOT
export OMEGA_ROOT

case "${JOB_SCHEDULER}" in
  SLURM)
    sbatch \
      --job-name=OmegaCdash \
      --output="${CRONJOB_LOGDIR}/omega_cdash_%j.out" \
      --error="${CRONJOB_LOGDIR}/omega_cdash_%j.err" \
      "${HERE}/job_${CRONJOB_MACHINE}_omega_cdash.sbatch"
    ;;

  PBS)
    qsub \
      -N OmegaCdash \
      -V \
      -o "${CRONJOB_LOGDIR}/" \
      -e "${CRONJOB_LOGDIR}/" \
      "${HERE}/job_${CRONJOB_MACHINE}_omega_cdash.pbs"
    ;;

  *)
    echo "Error: Unsupported job scheduler '${JOB_SCHEDULER}'." >&2
    exit 1
    ;;
esac

echo "[$(date)] Finished $SCRIPT_NAME"
