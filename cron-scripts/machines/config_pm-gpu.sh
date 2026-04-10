#!/usr/bin/env bash

set -eo pipefail

module load cray-python cmake

export CRONJOB_BASEDIR=/pscratch/sd/${USER:0:1}/${USER}/omega/cronjobs_pm-gpu
export E3SM_COMPILERS="gnugpu"

mkdir -p "$CRONJOB_BASEDIR"
