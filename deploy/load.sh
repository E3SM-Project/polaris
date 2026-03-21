# bash snippet for adding Polaris-specific environment variables

# we need a special approach for cray machines ($POLARIS_MACHINE), notably
# pm-cpu and pm-gpu
if [ "$POLARIS_MACHINE" = "pm-cpu" ] || [ "$POLARIS_MACHINE" = "pm-gpu" ]; then
    export NETCDF=${CRAY_NETCDF_HDF5PARALLEL_PREFIX}
    export NETCDFF=${CRAY_NETCDF_HDF5PARALLEL_PREFIX}
    export PNETCDF=${CRAY_PARALLEL_NETCDF_PREFIX}
else
    export NETCDF=$(dirname $(dirname $(which nc-config)))
    export NETCDFF=$(dirname $(dirname $(which nf-config)))
    export PNETCDF=$(dirname $(dirname $(which pnetcdf-config)))
fi

export PIO=${MACHE_DEPLOY_SPACK_LIBRARY_VIEW}
export METIS_ROOT=${MACHE_DEPLOY_SPACK_LIBRARY_VIEW}
export PARMETIS_ROOT=${MACHE_DEPLOY_SPACK_LIBRARY_VIEW}

export USE_PIO2=true
export OPENMP=true
export HDF5_USE_FILE_LOCKING=FALSE
