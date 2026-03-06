#!/usr/bin/env bash
set -eo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_NAME="$(basename "${BASH_SOURCE[0]}")"
echo "[$(date)] Starting $SCRIPT_NAME"

export OMEGA_CDASH_BASEDIR=${CRONJOB_BASEDIR}/tasks/omega_cdash
export TESTROOT="${OMEGA_CDASH_BASEDIR}/tests"
mkdir -p $OMEGA_CDASH_BASEDIR
mkdir -p $TESTROOT

export OMEGA_HOME="${OMEGA_CDASH_BASEDIR}/Omega"

if [[ ! -d $OMEGA_HOME ]]; then
    cd ${OMEGA_CDASH_BASEDIR}
    git clone https://github.com/E3SM-Project/Omega.git
fi

cd ${OMEGA_HOME}
git checkout develop
git fetch origin
git reset --hard origin/develop
git submodule update --init --recursive || true

if [[ ! -f ${TESTROOT}/OmegaMesh.nc ]]; then
    wget -O ${TESTROOT}/OmegaMesh.nc https://web.lcrc.anl.gov/public/e3sm/inputdata/ocn/mpas-o/oQU240/ocean.QU.240km.151209.nc
fi

if [[ ! -f ${TESTROOT}/OmegaSphereMesh.nc ]]; then
    wget -O ${TESTROOT}/OmegaSphereMesh.nc https://web.lcrc.anl.gov/public/e3sm/polaris/ocean/polaris_cache/global_convergence/icos/cosine_bell/Icos480/init/initial_state.230220.nc
fi

if [[ ! -f ${TESTROOT}/OmegaPlanarMesh.nc ]]; then
    wget -O ${TESTROOT}/OmegaPlanarMesh.nc https://gist.github.com/mwarusz/f8caf260398dbe140d2102ec46a41268/raw/e3c29afbadc835797604369114321d93fd69886d/PlanarPeriodic48x48.nc
fi

sbatch \
  --job-name=OmegaCdash \
  --output="$CRONJOB_LOGDIR/omega_cdash_%j.out" \
  --error="$CRONJOB_LOGDIR/omega_cdash_%j.err" \
  ${HERE}/job_${CRONJOB_MACHINE}_omega_cdash.sbatch

echo "[$(date)] Finished $SCRIPT_NAME"
