"""Compatibility repository around the existing sqlite helpers.

The first FastAPI migration keeps the proven sqlite functions in local_db.py
behind a repository boundary. Individual tables can now be moved to
SQLAlchemy models incrementally without changing the HTTP layer.
"""

import local_db

