#!/usr/bin/env bash

set -eo pipefail

module load cray-python cmake

export CRONJOB_BASEDIR=/pscratch/sd/${USER:0:1}/${USER}/omega/cronjobs_pm-cpu
export E3SM_COMPILERS="gnu"

mkdir -p "$CRONJOB_BASEDIR"
