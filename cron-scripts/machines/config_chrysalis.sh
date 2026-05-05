#!/usr/bin/env bash

set -euo pipefail

source /etc/bashrc
module load python cmake

export CRONJOB_BASEDIR="${POLARIS_CRON_ROOT:?POLARIS_CRON_ROOT must be set}"

declare -A COMPILER_MAP

# Add archs
COMPILER_MAP["gnu"]="SERIAL"
COMPILER_MAP["intel"]="SERIAL"

export COMPILER_MAP_DEF=$(declare -p COMPILER_MAP)

mkdir -p "$CRONJOB_BASEDIR"
