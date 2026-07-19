"""Compatibility repository around the existing MySQL helpers.

The repository boundary stays in place so the HTTP layer does not need to
change while the backend continues to use ``local_db.py``.
"""

import local_db
