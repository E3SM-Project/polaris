#!/usr/bin/env bash

set -eo pipefail

module load cray-python cmake

export all_proxy=socks://proxy.ccs.ornl.gov:3128/
export ftp_proxy=ftp://proxy.ccs.ornl.gov:3128/
export http_proxy=http://proxy.ccs.ornl.gov:3128/
export https_proxy=http://proxy.ccs.ornl.gov:3128/
export no_proxy='localhost,127.0.0.0/8,*.ccs.ornl.gov'

export CRONJOB_BASEDIR=/lustre/orion/cli115/scratch/${USER}/cronjobs

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
