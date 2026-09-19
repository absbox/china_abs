"""Load the sibling subproject the dashboard still needs.

The dashboard is status/health-only, so the only cross-project dependency is
the ``scheduler`` package, whose ``jobs.health`` module provides the
outstanding-work check and whose ``jobs.digest`` module is imported alongside
it.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def scheduler():
    """Return ``(jobs.digest, jobs.health)`` from the scheduler project."""
    path = str(ROOT / "scheduler")
    if path not in sys.path:
        sys.path.insert(0, path)
    import jobs.digest as digest
    import jobs.health as health

    return digest, health
