#!/usr/bin/env bash

set -eo pipefail

module load cray-python cmake

export all_proxy=socks://proxy.ccs.ornl.gov:3128/
export ftp_proxy=ftp://proxy.ccs.ornl.gov:3128/
export http_proxy=http://proxy.ccs.ornl.gov:3128/
export https_proxy=http://proxy.ccs.ornl.gov:3128/
export no_proxy='localhost,127.0.0.0/8,*.ccs.ornl.gov'

export CRONJOB_BASEDIR=/lustre/orion/cli115/scratch/grnydawn/cronjobs
export E3SM_COMPILERS="craygnu-mphipcc craycray-mphipcc crayamd-mphipcc craygnu craycray crayamd"

mkdir -p "$CRONJOB_BASEDIR"
