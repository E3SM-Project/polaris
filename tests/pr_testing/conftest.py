import sys
from pathlib import Path

SHARED_DIR = Path(__file__).resolve().parents[2] / 'utils' / 'pr_testing'

# the utilities' modules import each other by name, as they do when a
# utility's script runs
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))
