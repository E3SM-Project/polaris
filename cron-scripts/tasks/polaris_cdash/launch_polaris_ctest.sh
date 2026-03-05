#!/bin/bash -l
set -eo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_NAME="$(basename "${BASH_SOURCE[0]}")"
echo "[$(date)] Starting $SCRIPT_NAME"

POLARIS_CDASH_BASEDIR=${CRONJOB_BASEDIR}/tasks/polaris_cdash
POLARIS_CDASH_TESTDIR="${POLARIS_CDASH_BASEDIR}/tests"
OMEGA_HOME="${POLARIS_CDASH_BASEDIR}/polaris/e3sm_submodules/Omega"
MINIFORGE3_HOME="${POLARIS_CDASH_BASEDIR}/miniforge3"

mkdir -p $POLARIS_CDASH_BASEDIR
mkdir -p $POLARIS_CDASH_TESTDIR

if [[ "$CRONJOB_MACHINE" == "chrysalis" ]]; then
    module load python cmake
    PARMETIS_TPL=/lcrc/soft/climate/polaris/chrysalis/spack/dev_polaris_0_10_0_COMPILER_openmpi/var/spack/environments/dev_polaris_0_10_0_COMPILER_openmpi/.spack-env/view

elif [[ "$CRONJOB_MACHINE" == "frontier" ]]; then
    module load cray-python cmake git-lfs
	PARMETIS_TPL="/ccs/proj/cli115/software/polaris/frontier/spack/dev_polaris_0_10_0_COMPILER_mpich/var/spack/environments/dev_polaris_0_10_0_COMPILER_mpich/.spack-env/view"

elif [[ "$CRONJOB_MACHINE" == "pm-gpu" ]]; then
    module load cray-python cmake
    PARMETIS_TPL="/global/cfs/cdirs/e3sm/software/polaris/pm-gpu/spack/dev_polaris_0_10_0_COMPILER_mpich/var/spack/environments/dev_polaris_0_10_0_COMPILER_mpich/.spack-env/view"

elif [[ "$CRONJOB_MACHINE" == "pm-cpu" ]]; then
    module load cray-python cmake
    PARMETIS_TPL="/global/cfs/cdirs/e3sm/software/polaris/pm-cpu/spack/dev_polaris_0_10_0_COMPILER_mpich/var/spack/environments/dev_polaris_0_10_0_COMPILER_mpich/.spack-env/view"

elif [[ "$CRONJOB_MACHINE" == "unknown" ]]; then
  echo "CRONJOB_MACHINE is not set."
  exit -1

else
  echo "It seems that the cron job is not configured with CRONJOB_MACHINE."
  exit -1

fi

# ==============================================================================
# Functions
# ==============================================================================

install_miniforge3() {

if [ ! -d "$MINIFORGE3_HOME" ]; then
    echo "Installing Miniforge3..."
    pushd "$POLARIS_CDASH_BASEDIR" > /dev/null
    wget https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
    bash Miniforge3-Linux-x86_64.sh -b -p $MINIFORGE3_HOME
    popd > /dev/null
fi

}

setup_polaris_repo() {
    echo "================================================================================"
    echo "STEP 1: Setting up Polaris Repo (Baseline)"
    echo "================================================================================"
    cd "${POLARIS_CDASH_BASEDIR}"
    
    # Check if we are inside the 'polaris' folder or need to enter it
    if [ ! -d "polaris" ]; then
        echo "Cloning Polaris repository..."
        git clone git@github.com:E3SM-Project/polaris.git
        cd polaris
    else
        cd polaris
        echo "Repository exists. Resetting to main branch..."
        git fetch origin
        git checkout main
        git reset --hard origin/main
    fi
    
    echo "Updating specific submodules (jigsaw-python, Omega)..."
    git submodule update --init --recursive jigsaw-python
    git submodule update --init --recursive e3sm_submodules/Omega
}

configure_polaris() {
    local compiler=$1

    echo "--------------------------------------------------------------------------------"
    echo "Configuring Polaris for $compiler"
    echo "--------------------------------------------------------------------------------"
    
    cd "${POLARIS_CDASH_BASEDIR}/polaris"

    if [ ! -f "configure_polaris_envs.py" ]; then
        echo "Error: configure_polaris_envs.py not found in $(pwd)"
        exit 1
    fi

    if ! ls load_dev_polaris_*_${CRONJOB_MACHINE}_${compiler}_*.sh >/dev/null 2>&1; then
        echo "Configuring Polaris Environment"
        ./configure_polaris_envs.py --conda "${MINIFORGE3_HOME}" \
            -c "${compiler}" -m "${CRONJOB_MACHINE}"
    fi
}

build_omega_dev() {
    local compiler=$1
    local omega_build=$2
    local parmetis_path=$3

    echo "--------------------------------------------------------------------------------"
    echo "Building Omega (dev) with $compiler in $omega_build"
    echo "--------------------------------------------------------------------------------"


    rm -rf "$omega_build"
    mkdir -p "$omega_build"
    pushd "$omega_build" > /dev/null

    cmake \
      -DOMEGA_CIME_MACHINE="${CRONJOB_MACHINE}" \
      -DOMEGA_CIME_COMPILER="${compiler}" \
      -DOMEGA_BUILD_TEST=ON \
      -DOMEGA_PARMETIS_ROOT="${parmetis_path}" \
      "${OMEGA_HOME}/components/omega"

    source ./omega_env.sh

    ctest -M Nightly -T Start
    ctest -M Nightly -T Build
    #./omega_build.sh
    popd > /dev/null
}

run_baseline_suite() {
    local compiler=$1
    local omega_build=$2

    local polaris_build="${POLARIS_CDASH_TESTDIR}/${compiler}/polaris_build"

    # Clean up previous baseline directory to avoid stale logs
    if [ -d "$polaris_build" ]; then
        echo "Removing previous polaris build directory: $polaris_build"
        rm -rf "$polaris_build"
    fi

    mkdir -p "$polaris_build"

    pushd "$polaris_build" > /dev/null

    echo "--------------------------------------------------------------------------------"
    echo "Running Polaris Baseline Suite for $compiler"
    echo "--------------------------------------------------------------------------------"
    
    cd ""

    local env_file=$(ls ${POLARIS_CDASH_BASEDIR}/polaris/load_dev_polaris_*_${CRONJOB_MACHINE}_${compiler}_*.sh | head -n 1)
    if [ -f "$env_file" ]; then
        echo "Sourcing $env_file"
        source "$env_file"
    else
        echo "Warning: Environment file matching 'load_dev_polaris_*_${CRONJOB_MACHINE}_${compiler}_*.sh' not found."
    fi

    # Set up baseline suite
    polaris suite -c ocean -t omega_nightly --model omega \
        -w "$polaris_build" \
        -p "$omega_build"

#        --clean_build


    # Submit baseline job
    if [ -d "$polaris_build" ]; then
        cd "$polaris_build"
        echo "Submitting baseline job in $(pwd)..."
        # Fire and forget / continue on error
        sbatch --wait job_script.omega_pr.sh || true
    else
        echo "Error: Baseline directory $polaris_build was not created."
    fi
}

# ==============================================================================
# Main Execution
# ==============================================================================
install_miniforge3
setup_polaris_repo

for COMPILER in ${E3SM_COMPILERS}; do
    echo "################################################################################"
    echo "Processing Baseline for COMPILER: $COMPILER"
    echo "################################################################################"
    
    MAIN_LOG="${CRONJOB_LOGDIR}/polaris_cdash_main_${CRONJOB_DATE}.log"

    echo "Starting $COMPILER... logging to $MAIN_LOG"

    DEVELOP_BUILD="${POLARIS_CDASH_TESTDIR}/${COMPILER}/omega_build"

    # Capture Block
    {
        configure_polaris "$COMPILER"

        PARMETIS_HOME="${PARMETIS_TPL//COMPILER/$COMPILER}"
		if [ ! -f "$PARMETIS_HOME" ]; then
			if [[ "$CRONJOB_MACHINE" == "frontier" ]]; then
				PARMETIS_HOME=/ccs/proj/cli115/software/polaris/frontier/spack/dev_polaris_0_10_0_craygnu-mphipcc_mpich/var/spack/environments/dev_polaris_0_10_0_craygnu-mphipcc_mpich/.spack-env/view
            fi
		fi

        build_omega_dev "$COMPILER" "$DEVELOP_BUILD" "$PARMETIS_HOME"
        
        run_baseline_suite "$COMPILER" "$DEVELOP_BUILD"
    } 2>&1 | tee "$MAIN_LOG"
    
    # CDash Submission Logic
    BUILD_ID=$(date +%s)
    
    CASE_OUTPUTS_DIR="${POLARIS_CDASH_TESTDIR}/${COMPILER}/polaris_build/case_outputs"

    CDASH_DIR="${POLARIS_CDASH_TESTDIR}/${COMPILER}/cdash"
    echo "Creating CDash directory: $CDASH_DIR"
    rm -rf "$CDASH_DIR"
    mkdir -p "$CDASH_DIR"

    echo "Submitting results to CDash..."
    if [ -f "${HERE}/polaris_cdash.py" ]; then
        python3 "${HERE}/polaris_cdash.py" \
           --log-dir "$CASE_OUTPUTS_DIR" \
           --output-dir "$CDASH_DIR" \
           --results-dir "$DEVELOP_BUILD/Testing" \
           --site-name "$CRONJOB_MACHINE" \
           --build-name "Baseline_${COMPILER}" \
           --build-id "$BUILD_ID"
    else
        echo "Error: polaris_cdash.py not found at ${HERE}/polaris_cdash.py"
    fi
    
    echo "Running CTest submission from $CDASH_DIR..."
    if [ -f "${HERE}/CTestScript.txt" ]; then
         cp "${HERE}/CTestScript.txt" "$CDASH_DIR/"
         pushd "$CDASH_DIR" > /dev/null
         module load cmake && ctest -S CTestScript.txt -V
         popd > /dev/null
    else
         echo "Warning: CTestScript.txt not found in ${HERE}"
    fi
    
    echo "Finished Baseline processing for $COMPILER"
done

echo "[$(date)] Finished $SCRIPT_NAME"
