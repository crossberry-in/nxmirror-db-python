"""nxmirror-db — official Python SDK for the NxMirror DB platform.

Zero runtime dependencies (standard library only), Python 3.8+.

Quick start::

    from nxmirror_db import connect

    db = connect(database_id="nxdb-...", password="...")
    db.exec("CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, body TEXT)")
    res = db.query("INSERT INTO notes (body) VALUES (?)", ["hello"])
    print(res["lastInsertRowid"])

Docs: https://nxmirror.netlify.app/docs
"""
from .client import (
    DEFAULT_API_BASE,
    RESUMABLE_MAX_TOTAL,
    RESUMABLE_PART_SIZE,
    SDK_VERSION,
    SINGLE_UPLOAD_MAX,
    NxDatabase,
    NxError,
    NxWatchHandle,
    connect,
)
from .nosql import NxNoSql
from .query_builder import NxQueryBuilder
from .storage import NxStorage

__all__ = [
    "DEFAULT_API_BASE",
    "RESUMABLE_MAX_TOTAL",
    "RESUMABLE_PART_SIZE",
    "SDK_VERSION",
    "SINGLE_UPLOAD_MAX",
    "NxDatabase",
    "NxError",
    "NxNoSql",
    "NxQueryBuilder",
    "NxStorage",
    "NxWatchHandle",
    "connect",
]

__version__ = SDK_VERSION
