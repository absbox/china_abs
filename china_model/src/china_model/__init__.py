"""china_model — shared Peewee schema and DB access for the ABS pipeline.

Importing this package has no side effects.  Call :func:`configure` once at
application startup to bind the models to a database, then import the models
and helpers you need::

    import china_model
    china_model.configure()

    from china_model import Deal, Bond, QiniuStorage, Mineru
"""

from .db import check_connection, configure, db, is_configured
from .models import *  # noqa: F401,F403
