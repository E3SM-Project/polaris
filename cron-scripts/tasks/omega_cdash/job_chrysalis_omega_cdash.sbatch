#!/bin/bash -l
#SBATCH  --nodes=1
#SBATCH  --qos=high
#SBATCH  --time 02:00:00

if [ -f /etc/bashrc ]; then
    source /etc/bashrc
fi

TARGET_SCRIPT="$RUNSCRIPT_DIR/run_omega_cdash.sh"

if [ -f "$TARGET_SCRIPT" ]; then
    echo "Running script from: $TARGET_SCRIPT"
    exec bash "$TARGET_SCRIPT"
else
    echo "Error: $TARGET_SCRIPT not found."
    echo "Current directory: $(pwd)"
    echo "RUNSCRIPT_DIR: $RUNSCRIPT_DIR"
    exit 1
fi
