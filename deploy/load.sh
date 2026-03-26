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

export USE_PIO2=true
export OPENMP=true
export HDF5_USE_FILE_LOCKING=FALSE
