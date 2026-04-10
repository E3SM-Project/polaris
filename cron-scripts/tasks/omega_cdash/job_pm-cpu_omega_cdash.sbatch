#!/bin/bash -l
#SBATCH  --job-name=OmegaSCron
#SBATCH  --nodes=1
#SBATCH  --ntasks-per-node=64
#SBATCH  --output=/global/cfs/cdirs/e3sm/omega/cronjbos_pm-cpu/logs/OmegaSCronCPU_%j.out
#SBATCH  --error=/global/cfs/cdirs/e3sm/omega/cronjobs_pm-cpu/logs/OmegaSCronCPU_%j.err
#SBATCH  --constraint=cpu
#SBATCH  --account=e3sm
#SBATCH  --qos regular
#SBATCH  --exclusive
#SBATCH  --time 01:00:00


source /etc/bashrc

exec bash $(dirname "$0")/run_omega_cdash.sh
