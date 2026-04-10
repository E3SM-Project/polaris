#!/bin/bash -l
#SBATCH  --nodes=1
#SBATCH  -q debug
#SBATCH  --account=cli115
#SBATCH  --time 02:00:00


source /etc/bashrc

exec bash $(dirname "$0")/run_omega_cdash.sh
