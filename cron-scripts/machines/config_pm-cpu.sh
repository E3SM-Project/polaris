#!/usr/bin/env bash

set -eo pipefail

module load cray-python cmake

export CRONJOB_BASEDIR=/pscratch/sd/${USER:0:1}/${USER}/omega/cronjobs_pm-cpu
export E3SM_COMPILERS="gnu"

declare -A COMPILER_MAP

# Add archs
COMPILER_MAP["gnu"]="SERIAL"

export COMPILER_MAP_DEF=$(declare -p COMPILER_MAP)

mkdir -p "$CRONJOB_BASEDIR"
