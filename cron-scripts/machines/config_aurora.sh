#!/usr/bin/env bash

set -eo pipefail

source /usr/share/lmod/8.7.59/init/bash

export MODULEPATH="/opt/aurora/26.26.0/spack/unified/1.1.1/install/modulefiles/mpich/5.0.0.aurora_test.3c70a61-hlkigtk/Core:/opt/aurora/26.26.0/spack/unified/1.1.1/install/modulefiles/mpich/5.0.0.aurora_test.3c70a61-hlkigtk/intel-oneapi-compilers/2025.3.1:/opt/aurora/26.26.0/spack/unified/1.1.1/install/modulefiles/Core:/opt/aurora/26.26.0/spack/unified/1.1.1/install/modulefiles/intel-oneapi-compilers/2025.3.1:/usr/share/lmod/modulefiles/Linux:/usr/share/lmod/modulefiles/Core:/usr/share/lmod/lmod/modulefiles/Core:/opt/cray/pals/lmod/modulefiles/core:/opt/cray/modulefiles:/opt/aurora/26.26.0/modulefiles:/opt/aurora/25.190.0/modulefiles"

export PATH=/opt/pbs/bin:$PATH

module load cmake

export CRONJOB_BASEDIR="${POLARIS_CRON_ROOT:?POLARIS_CRON_ROOT must be set}"

declare -A COMPILER_MAP

# Add archs
COMPILER_MAP["oneapi-ifxgpu"]="SYCL"

export COMPILER_MAP_DEF=$(declare -p COMPILER_MAP)
export JOB_SCHEDULER=PBS

mkdir -p "$CRONJOB_BASEDIR"
