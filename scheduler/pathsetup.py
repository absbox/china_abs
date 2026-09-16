"""Path bootstrap for the scheduler subproject.

``docToCloud`` is a flat-module project (``chinabond.py``, ``cloud.py``,
``db.py``), not an installable package.  Importing this module first puts its
directory on ``sys.path`` so the scheduler jobs can reuse that logic directly.
"""

from __future__ import annotations

import sys
from pathlib import Path

SCHEDULER_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCHEDULER_DIR.parent
DOCTOCLOUD_DIR = REPO_ROOT / "docToCloud"

if str(DOCTOCLOUD_DIR) not in sys.path:
    sys.path.insert(0, str(DOCTOCLOUD_DIR))
