import os as _os

# Hold the numerical thread pools to one before anything imports numpy.
#
# This has to be the first thing in the package, above the imports below.
# OpenBLAS sizes its pool when numpy is first imported and nothing resizes it
# afterwards without `threadpoolctl`, which Polaris does not depend on; a
# forked child inherits whatever the parent built, so the concurrent path
# cannot decide it later either.  Putting this in `polaris/__main__.py` was
# tried and is too late: importing that module imports this package first,
# and the process already has 129 OS threads by the time it runs.
#
# Polaris asks nothing of a threaded BLAS.  Every `np.linalg` call in the
# framework is a vector norm over a one-dimensional array, `polyfit` runs on
# a handful of convergence points, and the one `matmul` is a stack of tiny
# per-point matrices.  What the pool does cost is reproducibility: a threaded
# reduction sums in an order that depends on the thread count, so a serial
# run at one thread per core and a concurrent run at one thread would not
# agree in the last digits.  Pinning it is what lets the two paths agree by
# construction, and it is also what makes the scheduler safe to fork from.
#
# It says nothing about a model's threading.  `run_parallel_command()` sets
# `OMP_NUM_THREADS` from a step's `openmp_threads` for a launched command,
# which overrides this, and JIGSAW takes its count from `numthread` in its
# own config file rather than from the environment.
#
# `setdefault`, so that a job script or a developer that has deliberately
# chosen a different number keeps it.
for _pool in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
    _os.environ.setdefault(_pool, '1')

from polaris.component import Component as Component  # noqa: E402
from polaris.model_step import ModelStep as ModelStep  # noqa: E402
from polaris.step import Step as Step  # noqa: E402
from polaris.task import Task as Task  # noqa: E402
