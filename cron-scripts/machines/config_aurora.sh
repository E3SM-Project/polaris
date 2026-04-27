#!/usr/bin/env bash

set -eo pipefail

module load cmake

export CRONJOB_BASEDIR=$POLARIS_CRON_ROOT

declare -A COMPILER_MAP

# Add archs
COMPILER_MAP["oneapi-ifxgpu"]="SYCL"

export COMPILER_MAP_DEF=$(declare -p COMPILER_MAP)

mkdir -p "$CRONJOB_BASEDIR"
