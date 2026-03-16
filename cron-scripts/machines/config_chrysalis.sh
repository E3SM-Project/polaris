#!/usr/bin/env bash
set -eo pipefail

source /etc/bashrc

export CRONJOB_BASEDIR=/lcrc/globalscratch/${USER}/cronjobs
export E3SM_COMPILERS="gnu intel"

mkdir -p "$CRONJOB_BASEDIR"
