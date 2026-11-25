"""
A skip for tests that need CPU affinity, which only Linux has.

Polaris confines a step it runs to its cores with ``os.sched_setaffinity``,
and these tests check that by asking ``os.sched_getaffinity``.  Neither
exists on macOS, where steps run unconfined, so there is nothing to check.
"""

import os

import pytest

needs_affinity = pytest.mark.skipif(
    not hasattr(os, 'sched_getaffinity'),
    reason='needs CPU affinity (os.sched_getaffinity), which only Linux has',
)
