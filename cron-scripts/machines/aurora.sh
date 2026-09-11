# Shell environment for the nightly cron jobs on aurora, sourced by
# launch_all.sh.  Cron starts with almost no environment, so this provides
# what deploy.py and the tasks need before any Polaris environment exists.

# shellcheck disable=SC1091
source /usr/share/lmod/8.7.59/init/bash
export MODULEPATH="/opt/aurora/26.26.0/spack/unified/1.1.1/install/modulefiles/mpich/5.0.0.aurora_test.3c70a61-hlkigtk/Core:/opt/aurora/26.26.0/spack/unified/1.1.1/install/modulefiles/mpich/5.0.0.aurora_test.3c70a61-hlkigtk/intel-oneapi-compilers/2025.3.1:/opt/aurora/26.26.0/spack/unified/1.1.1/install/modulefiles/Core:/opt/aurora/26.26.0/spack/unified/1.1.1/install/modulefiles/intel-oneapi-compilers/2025.3.1:/usr/share/lmod/modulefiles/Linux:/usr/share/lmod/modulefiles/Core:/usr/share/lmod/lmod/modulefiles/Core:/opt/cray/pals/lmod/modulefiles/core:/opt/cray/modulefiles:/opt/aurora/26.26.0/modulefiles:/opt/aurora/25.190.0/modulefiles"

# qsub is not on cron's PATH
export PATH=/opt/pbs/bin:$PATH

module load python
