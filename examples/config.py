"""Shared helper for every example — zero dependencies.

Loads .env.local (created by 00_setup_database.py) or .env from the repo root
into os.environ, makes the local nxmirror_db package importable, and exposes
small helpers used by all examples.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent   # examples/
ROOT = HERE.parent                       # repo root

# make the local nxmirror_db package importable (repo checkout wins)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

for _name in (".env.local", ".env"):
    _p = ROOT / _name
    if not _p.exists():
        continue
    for _line in _p.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _key, _, _value = _line.partition("=")
        _key = _key.strip()
        _value = _value.strip().strip('"').strip("'")
        os.environ.setdefault(_key, _value)

API_BASE = os.environ.get("NX_API_BASE") or "https://nxmirror.netlify.app"


def _fail(what: str) -> None:
    print(
        f"""
Missing credentials: {what}

Pick ONE way to provide them:

  1. Easy:   python examples/00_setup_database.py
             (creates a demo account + 2 databases, writes .env.local)

  2. Manual: copy .env.example to .env.local and fill in your
             database ID + password from the NxMirror dashboard
             (https://nxmirror.netlify.app/dashboard/database)
""",
        file=sys.stderr,
    )
    sys.exit(1)


def sql_creds() -> dict:
    """Connection settings for the SQL (engine "sqlite") demo database."""
    database_id = os.environ.get("NXDB_ID")
    password = os.environ.get("NXDB_PASSWORD")
    if not database_id or not password:
        _fail("NXDB_ID and NXDB_PASSWORD")
    return {"databaseId": database_id, "password": password, "apiBase": API_BASE}


def nosql_creds() -> dict:
    """Connection settings for the NoSQL (engine "nosql") demo database."""
    database_id = os.environ.get("NXDB_NOSQL_ID")
    password = os.environ.get("NXDB_NOSQL_PASSWORD")
    if not database_id or not password:
        _fail("NXDB_NOSQL_ID and NXDB_NOSQL_PASSWORD")
    return {"databaseId": database_id, "password": password, "apiBase": API_BASE}


def banner(title: str) -> None:
    """Pretty banner so example output is easy to read."""
    print(f"\n== {title} ==")
