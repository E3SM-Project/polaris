#!/bin/bash -l
#SBATCH  --job-name=OmegaSCron
#SBATCH  --nodes=1
#SBATCH  --ntasks-per-node=8
#SBATCH  --gpus-per-node=4
#SBATCH  --constraint=gpu
#SBATCH  --account=e3sm_g
#SBATCH  --qos regular
#SBATCH  --exclusive
#SBATCH  --time 01:00:00

if [ -f /etc/bash.bashrc ]; then
    source /etc/bash.bashrc
fi

source /opt/cray/pe/lmod/8.7.60/init/sh

#SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)

# Check if the target script exists before executing
#TARGET_SCRIPT="$SCRIPT_DIR/run_omega_cdash.sh"
TARGET_SCRIPT="$RUNSCRIPT_DIR/run_omega_cdash.sh"

if [ -f "$TARGET_SCRIPT" ]; then
    echo "Running script from: $TARGET_SCRIPT"
    exec bash "$TARGET_SCRIPT"
else
    echo "Error: $TARGET_SCRIPT not found."
    echo "Current directory: $(pwd)"
    echo "Script directory: $SCRIPT_DIR"
    exit 1
fi

