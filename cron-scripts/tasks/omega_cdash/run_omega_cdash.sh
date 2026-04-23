#!/bin/bash -l

set -euo pipefail

echo "Starting omega cdash job"

if [[ "${CRONJOB_MACHINE:-unknown}" == "chrysalis" ]]; then
    module load python cmake
    PARMETIS_TPL="/lcrc/soft/climate/polaris/chrysalis/spack/dev_polaris_0_10_0_COMPILER_openmpi/var/spack/environments/dev_polaris_0_10_0_COMPILER_openmpi/.spack-env/view"

elif [[ "${CRONJOB_MACHINE:-unknown}" == "frontier" ]]; then
    module load cray-python cmake git-lfs
    PARMETIS_TPL="/ccs/proj/cli115/software/polaris/frontier/spack/dev_polaris_0_10_0_COMPILER_mpich/var/spack/environments/dev_polaris_0_10_0_COMPILER_mpich/.spack-env/view"

elif [[ "${CRONJOB_MACHINE:-unknown}" == "pm-gpu" ]]; then
    module load cray-python cmake
    PARMETIS_TPL="/global/cfs/cdirs/e3sm/software/polaris/pm-gpu/spack/dev_polaris_0_10_0_COMPILER_mpich/var/spack/environments/dev_polaris_0_10_0_COMPILER_mpich/.spack-env/view"

elif [[ "${CRONJOB_MACHINE:-unknown}" == "pm-cpu" ]]; then
    module load cray-python cmake
    PARMETIS_TPL="/global/cfs/cdirs/e3sm/software/polaris/pm-cpu/spack/dev_polaris_0_10_0_COMPILER_mpich/var/spack/environments/dev_polaris_0_10_0_COMPILER_mpich/.spack-env/view"

elif [[ "${CRONJOB_MACHINE:-unknown}" == "unknown" ]]; then
    echo "CRONJOB_MACHINE is not set."
    exit 1

else
    echo "It seems that the cron job is not configured with CRONJOB_MACHINE."
    exit -1

fi

#echo "Compilers and ARCHs: ${COMPILER_MAP}"
eval "$COMPILER_MAP_DEF"

for COMPILER in "${!COMPILER_MAP[@]}"; do

    WORKDIR=${TESTROOT}/${COMPILER}/${CRONJOB_DATE}
    rm -rf ${WORKDIR}
    mkdir -p ${WORKDIR}

    PARMETIS_HOME="${PARMETIS_TPL//COMPILER/$COMPILER}"
    if [ ! -d "$PARMETIS_HOME" ]; then
        if [[ "${CRONJOB_MACHINE:-unknown}" == "frontier" ]]; then
            PARMETIS_HOME="/ccs/proj/cli115/software/polaris/frontier/spack/dev_polaris_0_10_0_craygnu-mphipcc_mpich/var/spack/environments/dev_polaris_0_10_0_craygnu-mphipcc_mpich/.spack-env/view"
        fi
    fi

    cmake \
      -DOMEGA_CIME_MACHINE=${CRONJOB_MACHINE} \
      -DOMEGA_CIME_COMPILER=${COMPILER} \
      -DOMEGA_ARCH=${COMPILER_MAP[$COMPILER]} \
      -DOMEGA_BUILD_TEST=ON \
      -DOMEGA_PARMETIS_ROOT=${PARMETIS_HOME} \
      -S ${OMEGA_ROOT}/components/omega \
      -B ${WORKDIR};

    mkdir -p ${WORKDIR}/test

    ln -sf  ${TESTROOT}/OmegaMesh.nc ${WORKDIR}/test/OmegaMesh.nc
    ln -sf  ${TESTROOT}/OmegaSphereMesh.nc ${WORKDIR}/test/OmegaSphereMesh.nc
    ln -sf  ${TESTROOT}/OmegaPlanarMesh.nc ${WORKDIR}/test/OmegaPlanarMesh.nc

    source ${WORKDIR}/omega_env.sh

    ctest \
      -S ${OMEGA_ROOT}/components/omega/CTestScript.cmake \
      -DCTEST_SOURCE_DIRECTORY=${OMEGA_ROOT}/components/omega \
      -DCTEST_BINARY_DIRECTORY=${WORKDIR} \
      -DCTEST_SITE=${CRONJOB_MACHINE} \
      -DCTEST_BUILD_GROUP="Omega Unit-test" \
      -DCTEST_BUILD_NAME="unitest-develop-${COMPILER}" \
      -DCTEST_NIGHTLY_START_TIME="06:00:00 UTC" \
      -DCTEST_BUILD_COMMAND="${WORKDIR}/omega_build.sh" \
      -DCTEST_BUILD_CONFIGURATION="Release" \
      -DCTEST_DROP_SITE_CDASH=TRUE \
      -DCTEST_SUBMIT_URL="https://my.cdash.org/submit.php?project=E3SM";

done
