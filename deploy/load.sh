# bash snippet for adding Polaris-specific environment variables

_polaris_detect_prefix() {
    local helper="$1"

    if command -v "${helper}" >/dev/null 2>&1; then
        dirname "$(dirname "$(command -v "${helper}")")"
        return 0
    fi

    if [ -n "${CONDA_PREFIX:-}" ] && [ -d "${CONDA_PREFIX}" ]; then
        printf '%s\n' "${CONDA_PREFIX}"
        return 0
    fi

    return 1
}

# Temporary: on Aurora, mache 5.1.0 and later load oneAPI 2025.3.1 and mpich
# 51a9474, but Omega's CIME config still builds with oneAPI 2026.1.0 and the
# mpich it comes with, 87e2045, as the Spack environments are built (see
# deploy/spack/aurora_intel_mpich.yaml).  An Omega built with one and run with
# the other cannot find MKL (#896).  Load oneAPI first, which makes the mpich
# module visible.  Remove this once Omega moves to oneAPI 2025.3.1.
if [ "$POLARIS_MACHINE" = "aurora" ]; then
    module load oneapi/release/2026.1.0 >/dev/null 2>&1
    module load mpich/prd/5.0.0.aurora_test.87e2045 >/dev/null 2>&1
fi

_polaris_stack_root="${MACHE_DEPLOY_SPACK_LIBRARY_VIEW}"
if [ -z "${_polaris_stack_root}" ] && [ -n "${CONDA_PREFIX:-}" ]; then
    _polaris_stack_root="${CONDA_PREFIX}"
fi

# we need a special approach for cray machines ($POLARIS_MACHINE), notably
# pm-cpu and pm-gpu
if [ "$POLARIS_MACHINE" = "pm-cpu" ] || [ "$POLARIS_MACHINE" = "pm-gpu" ]; then
    export NETCDF=${CRAY_NETCDF_HDF5PARALLEL_PREFIX}
    export NETCDFF=${CRAY_NETCDF_HDF5PARALLEL_PREFIX}
    export PNETCDF=${CRAY_PARALLEL_NETCDF_PREFIX}
else
    if _polaris_detect_prefix nc-config >/dev/null 2>&1; then
        export NETCDF=$(_polaris_detect_prefix nc-config)
    fi
    if _polaris_detect_prefix nf-config >/dev/null 2>&1; then
        export NETCDFF=$(_polaris_detect_prefix nf-config)
    fi
    if command -v pnetcdf-config >/dev/null 2>&1; then
        export PNETCDF=$(dirname "$(dirname "$(command -v pnetcdf-config)")")
    elif [ -n "${CONDA_PREFIX:-}" ] && ls "${CONDA_PREFIX}"/lib/libpnetcdf* >/dev/null 2>&1; then
        export PNETCDF="${CONDA_PREFIX}"
    fi
fi

export PIO=${_polaris_stack_root}
export METIS_ROOT=${_polaris_stack_root}
export PARMETIS_ROOT=${_polaris_stack_root}

# Albany is only in Spack environments deployed with --with-albany.  Only MALI
# builds link to it, so it is left out of MPAS_EXTERNAL_LIBS.
_polaris_albany_flags="${MACHE_DEPLOY_SPACK_LIBRARY_VIEW:-}/export_albany.in"
if [ -n "${MACHE_DEPLOY_SPACK_LIBRARY_VIEW:-}" ] && \
   [ -f "${_polaris_albany_flags}" ]; then
    # shellcheck source=/dev/null
    source "${_polaris_albany_flags}"
    # Albany and Trilinos are shared libraries that nothing else puts on the
    # library path, so MALI gets an rpath to each library directory in this
    # Spack installation
    _polaris_spack_root="${MACHE_DEPLOY_SPACK_LIBRARY_VIEW%%/var/spack/*}"
    _polaris_rpaths=""
    for _polaris_flag in ${ALBANY_LINK_LIBS}; do
        case "${_polaris_flag}" in
            -L"${_polaris_spack_root}"/opt/*)
                case "${_polaris_rpaths} " in
                    *" -Wl,-rpath,${_polaris_flag#-L} "*) ;;
                    *) _polaris_rpaths="${_polaris_rpaths} -Wl,-rpath,${_polaris_flag#-L}" ;;
                esac
                ;;
        esac
    done
    _polaris_mpicxx=""
    if [ "$POLARIS_MPI" = "openmpi" ] && \
       [ "$POLARIS_MACHINE" = "chrysalis" ]; then
        _polaris_mpicxx="-lmpi_cxx"
    fi
    export POLARIS_ALBANY_LINK_LIBS="${ALBANY_LINK_LIBS}${_polaris_rpaths} -lstdc++ ${_polaris_mpicxx}"
    unset _polaris_spack_root _polaris_rpaths _polaris_flag _polaris_mpicxx
fi
unset _polaris_albany_flags

export USE_PIO2=true
export OPENMP=true
export HDF5_USE_FILE_LOCKING=FALSE
