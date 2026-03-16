#!/bin/bash -l
#SBATCH  --job-name=OmegaSCron
#SBATCH  --nodes=1
#SBATCH  --ntasks-per-node=8
#SBATCH  --gpus-per-node=4
#SBATCH  --output=/global/cfs/cdirs/e3sm/omega/cronjobs_pm-gpu/logs/OmegaSCronGPU_%j.out
#SBATCH  --error=/global/cfs/cdirs/e3sm/omega/cronjobs_pm-gpu/logs/OmegaSCronGPU_%j.err
#SBATCH  --constraint=gpu
#SBATCH  --account=e3sm_g
#SBATCH  --qos regular
#SBATCH  --exclusive
#SBATCH  --time 01:00:00


source /etc/bashrc

exec bash $(dirname "$0")/run_omega_cdash.sh
