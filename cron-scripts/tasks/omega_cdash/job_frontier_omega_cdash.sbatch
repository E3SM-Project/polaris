#!/bin/bash -l
#SBATCH  --nodes=1
#SBATCH  -q debug
#SBATCH  --account=cli115
#SBATCH  --time 02:00:00

if [ -f /etc/bash.bashrc ]; then
    source /etc/bash.bashrc
fi

export all_proxy=socks://proxy.ccs.ornl.gov:3128/
export ftp_proxy=ftp://proxy.ccs.ornl.gov:3128/
export http_proxy=http://proxy.ccs.ornl.gov:3128/
export https_proxy=http://proxy.ccs.ornl.gov:3128/
export no_proxy='localhost,127.0.0.0/8,*.ccs.ornl.gov'

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
