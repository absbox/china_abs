"""Backwards-compatible shim.

The schema now lives in the :mod:`china_model` package.  This module exists so
existing ``from model import ...`` imports keep working during the migration.

Unlike the old module this is side-effect free: importing it does **not**
connect to a database.  Call ``china_model.configure()`` at startup.
"""

from china_model import *  # noqa: F401,F403
from china_model import configure, db, is_configured  # noqa: F401
