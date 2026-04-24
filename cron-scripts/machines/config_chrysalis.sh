#!/usr/bin/env bash
set -eo pipefail

source /etc/bashrc

export CRONJOB_BASEDIR=$POLARIS_CRON_ROOT
export E3SM_COMPILERS="gnu intel"

mkdir -p "$CRONJOB_BASEDIR"
