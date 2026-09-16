"""Scheduled jobs, ported from ``flow/dags`` onto the new subprojects."""

import sys
from pathlib import Path

# Make the scheduler directory importable so ``import pathsetup`` works no
# matter how this package is entered, then let pathsetup expose docToCloud.
_SCHEDULER_DIR = Path(__file__).resolve().parent.parent
if str(_SCHEDULER_DIR) not in sys.path:
    sys.path.insert(0, str(_SCHEDULER_DIR))

import pathsetup  # noqa: E402,F401  (adds docToCloud to sys.path)
