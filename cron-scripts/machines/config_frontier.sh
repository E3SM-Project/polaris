#!/usr/bin/env bash

set -eo pipefail

module load cray-python cmake

export CRONJOB_BASEDIR=$POLARIS_CRON_ROOT

declare -A COMPILER_MAP

# Add archs
COMPILER_MAP["craygnu-mphipcc"]="HIP"
COMPILER_MAP["craycray-mphipcc"]="HIP"
COMPILER_MAP["crayamd-mphipcc"]="HIP"
COMPILER_MAP["craygnu"]="SERIAL"
COMPILER_MAP["craycray"]="SERIAL"
COMPILER_MAP["crayamd"]="SERIAL"

export COMPILER_MAP_DEF=$(declare -p COMPILER_MAP)

mkdir -p "$CRONJOB_BASEDIR"
