"""Compatibility shim.

The Peewee schema now lives in the shared :mod:`china_model` package.  This
module keeps the historical ``from model import ...`` imports working and,
for backwards compatibility with the old module, binds the database on import
when the application has not already done so.

New code should import from ``china_model`` directly.
"""

import china_model

if not china_model.is_configured():
    china_model.configure()

from china_model import *  # noqa: F401,F403,E402
from china_model import configure, db, is_configured  # noqa: F401,E402
