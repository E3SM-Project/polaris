import sys
from pathlib import Path

TASKS_DIR = Path(__file__).resolve().parents[2] / 'cron-scripts' / 'tasks'

# the tasks' modules import each other by name, as they do when a task's
# script runs
if str(TASKS_DIR) not in sys.path:
    sys.path.insert(0, str(TASKS_DIR))
