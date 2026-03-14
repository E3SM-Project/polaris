#!/usr/bin/env bash

set -eo pipefail

module load cray-python cmake

export CRONJOB_BASEDIR=/pscratch/sd/y/youngsun/omega/cronjobs_pm-cpu
export E3SM_COMPILERS="gnu"

mkdir -p "$CRONJOB_BASEDIR"
