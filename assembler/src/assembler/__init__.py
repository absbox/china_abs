"""assembler — fill deal data from the ``os_fill_*`` reporting views.

The shared :mod:`china_model` package owns the ORM and the connection pool.
Importing this package has no database side effects; call
:func:`assembler.db.ensure_configured` (or simply run a fill function, which
does it for you) to bind the models.
"""

from __future__ import annotations

from . import fill
from .db import ensure_configured, q_with_m

__all__ = ["fill", "ensure_configured", "q_with_m"]
