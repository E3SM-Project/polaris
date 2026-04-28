#!/usr/bin/env bash
set -euo pipefail

source /etc/bashrc

export CRONJOB_BASEDIR="${POLARIS_CRON_ROOT:?POLARIS_CRON_ROOT must be set}"
export E3SM_COMPILERS="gnu intel"

mkdir -p "$CRONJOB_BASEDIR"
