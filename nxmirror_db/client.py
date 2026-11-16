"""NxMirror DB SDK — client core (official Python port of the nxmirror-db JS SDK).

Zero runtime dependencies: uses only the Python standard library (urllib).
Python 3.8+.

Quick start::

    from nxmirror_db import connect

    db = connect(database_id="nxdb-...", password="...")
    res = db.query("SELECT * FROM users WHERE active = ?", [True])
    print(res["rows"])
"""
from __future__ import annotations

import json as _json
import re as _re
import threading as _threading
import time as _time
import urllib.error as _urlerror
import urllib.parse as _urlparse
import urllib.request as _urlrequest
from typing import Any, Callable, Dict, List, Optional

from .errors import NxError, RESUMABLE_MAX_TOTAL, RESUMABLE_PART_SIZE, SINGLE_UPLOAD_MAX
from .nosql import NxNoSql
from .query_builder import NxQueryBuilder
from .storage import NxStorage

DEFAULT_API_BASE = "https://nxmirror.netlify.app/api"
SDK_VERSION = "1.0.0"

__all__ = ["NxDatabase", "NxError", "NxWatchHandle", "connect",
           "DEFAULT_API_BASE", "SDK_VERSION", "SINGLE_UPLOAD_MAX",
           "RESUMABLE_PART_SIZE", "RESUMABLE_MAX_TOTAL"]

class NxWatchHandle:
    """Control handle returned by :meth:`NxDatabase.watch`."""

    def __init__(self, event: _threading.Event):
        self._event = event

    def unsubscribe(self) -> None:
        self._event.set()

    @property
    def stopped(self) -> bool:
        return self._event.is_set()


def detect_api_base(base: Optional[str]) -> str:
    trimmed = str(base or DEFAULT_API_BASE).rstrip("/")
    return trimmed if trimmed.endswith("/api") else trimmed + "/api"


class NxDatabase:
    """Client for one NxMirror DB database.

    Auth: pass ``password`` (full access, trusted servers only), ``token``
    (scoped API token), or ``appId`` + ``appToken`` (browser / embedded apps).
    Both camelCase and snake_case keyword names are accepted.
    """

    def __init__(
        self,
        databaseId: Optional[str] = None,
        password: Optional[str] = None,
        token: Optional[str] = None,
        appId: Optional[str] = None,
        appToken: Optional[str] = None,
        apiBase: Optional[str] = None,
        timeoutMs: int = 30000,
        retries: int = 2,
        *,
        database_id: Optional[str] = None,
        api_base: Optional[str] = None,
        timeout_ms: Optional[int] = None,
        app_id: Optional[str] = None,
        app_token: Optional[str] = None,
    ):
        database_id = database_id or databaseId
        app_id = app_id or appId
        app_token = app_token or appToken
        timeout_ms = timeout_ms if timeout_ms is not None else timeoutMs
        if not database_id:
            raise NxError("NxDB.connect requires a databaseId.", "invalid_input")
        if not password and not token and not (app_id and app_token):
            raise NxError("Provide a token, a password, or an appId + appToken.", "invalid_input")
        self.database_id = str(database_id)
        self.api_base = detect_api_base(api_base or apiBase)
        self.timeout_ms = int(timeout_ms)
        self.retries = min(5, max(0, int(retries if retries is not None else 2)))
        self._auth = {"password": password, "token": token, "appId": app_id, "appToken": app_token}
        self.engine: Optional[str] = None
        self.permissions: Optional[List[str]] = None
        self.storage = NxStorage(self)
        self.nosql = NxNoSql(self)

    # ---------------- transport ----------------

    def _headers(self) -> Dict[str, str]:
        h = {"x-nxdb-id": self.database_id}
        if self._auth["token"]:
            h["Authorization"] = "Bearer " + self._auth["token"]
        if self._auth["password"]:
            h["x-nxdb-password"] = self._auth["password"]
        if self._auth["appId"]:
            h["x-nxdb-app"] = self._auth["appId"]
            h["x-nxdb-app-token"] = self._auth["appToken"]
        return h

    def request(
        self,
        path: str,
        method: str = "GET",
        body: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        blob: bool = False,
        attempt: int = 0,
    ) -> Any:
        url = f"{self.api_base}/db/{path}"
        data = None
        req_headers = self._headers()
        if body is not None:
            data = _json.dumps(body, ensure_ascii=False).encode("utf-8")
            req_headers["Content-Type"] = "application/json"
        if headers:
            req_headers.update(headers)
        req = _urlrequest.Request(url, data=data, method=method, headers=req_headers)
        try:
            with _urlrequest.urlopen(req, timeout=self.timeout_ms / 1000.0) as resp:
                raw = resp.read()
        except _urlerror.HTTPError as e:
            status = int(e.code)
            raw = e.read()
            if status == 429:
                if attempt < self.retries:
                    try:
                        retry_after = float(e.headers.get("Retry-After") or 1)
                    except (TypeError, ValueError):
                        retry_after = 1.0
                    _time.sleep(retry_after)
                    return self.request(path, method, body, headers, blob, attempt + 1)
                raise NxError("NxDB rate limit exceeded. Slow down and retry shortly.", "rate_limited", 429) from None
            if status >= 500 and method == "GET" and attempt < self.retries:
                _time.sleep(0.4 * (attempt + 1))
                return self.request(path, method, body, headers, blob, attempt + 1)
            if blob and method == "GET" and (status == 404 or status >= 500) and attempt < self.retries:
                # Netlify Blobs replicas can serve a brief stale window right
                # after a write — retry idempotent blob GETs before giving up.
                _time.sleep(0.6 * (attempt + 1))
                return self.request(path, method, body, headers, blob, attempt + 1)
            text = raw.decode("utf-8", "replace")
            try:
                parsed = _json.loads(text) if text else {}
            except ValueError:
                parsed = {"error": text[:300]}
            if not isinstance(parsed, dict):
                parsed = {"error": text[:300]}
            message = parsed.get("error") or f"Request failed ({status})"
            code = parsed.get("code") or "request_failed"
            raise NxError(str(message), str(code), status) from None
        except (_urlerror.URLError, OSError) as e:
            reason = getattr(e, "reason", None) or e
            if method == "GET" and attempt < self.retries:
                _time.sleep(0.4 * (attempt + 1))
                return self.request(path, method, body, headers, blob, attempt + 1)
            raise NxError(f"Network error contacting NxDB: {reason}", "network_error") from None

        if blob:
            return raw
        text = raw.decode("utf-8", "replace")
        try:
            return _json.loads(text) if text else {}
        except ValueError:
            return {"error": text[:300]}

    # ---------------- engine guard ----------------

    def _assert_engine(self, expected: str) -> None:
        # engine is learned from connectInfo(); when unknown, let the server decide.
        if not self.engine or self.engine == expected:
            return
        hint = (
            'NoSQL document collections (db.nosql.*) need a database created with engine "nosql".'
            if expected == "nosql"
            else 'SQL calls (db.query / db.exec / db.table) need the "sqlite" engine — JSON documents live on engine "nosql" via db.nosql.*'
        )
        raise NxError(
            f'This database runs the "{self.engine}" engine — this call requires "{expected}". {hint}',
            "wrong_engine",
        )

    # ---------------- SQL ----------------

    def query(self, sql: str, params: Optional[List[Any]] = None) -> Dict[str, Any]:
        """Execute a parameterized SQL statement."""
        self._assert_engine("sqlite")
        result = self.request("query", method="POST", body={"databaseId": self.database_id, "sql": sql, "params": params or []})
        return {
            "rows": result.get("rows") or [],
            "columns": result.get("columns") or [],
            "changes": result.get("changes") or 0,
            "executionMs": result.get("executionMs") or 0,
            "truncated": bool(result.get("truncated")),
            "lastInsertRowid": result.get("lastInsertRowid"),
        }

    def exec(self, sql: str) -> Dict[str, Any]:
        """Execute a multi-statement SQL batch (no parameters)."""
        self._assert_engine("sqlite")
        result = self.request("query", method="POST", body={"databaseId": self.database_id, "sql": sql})
        return {"changes": result.get("changes") or 0, "executionMs": result.get("executionMs") or 0}

    def table(self, name: str) -> NxQueryBuilder:
        """Query builder entry point."""
        if not _re.fullmatch(r"\w+", str(name)):
            raise NxError("Invalid table name.", "invalid_input")
        return NxQueryBuilder(self, name)

    # ---------------- connection ----------------

    def connect_info(self) -> Dict[str, Any]:
        """Verify connectivity + permissions; learns the database engine."""
        info = self.request("connect", method="POST", body={"databaseId": self.database_id})
        self.permissions = info.get("permissions")
        self.engine = (info.get("database") or {}).get("engine")
        return {**info, "sdk": {"version": SDK_VERSION, "apiBase": self.api_base}}

    def details(self) -> Dict[str, Any]:
        """Database metadata + current table list."""
        return self.request("details", method="POST", body={"databaseId": self.database_id})

    # camelCase alias (JS SDK parity)
    connectInfo = connect_info

    # ---------------- realtime (change polling) ----------------

    def changes(self, table: Optional[str] = None, since: int = 0) -> Dict[str, Any]:
        """Fetch change events newer than a sequence number."""
        q: Dict[str, str] = {"db": self.database_id, "since": str(since)}
        if table:
            q["table"] = table
        result = self.request("events?" + _urlparse.urlencode(q))
        return {"events": result.get("events") or [], "latestSeq": result.get("latestSeq") or 0}

    def watch(
        self,
        table: Optional[str] = None,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        interval_ms: int = 5000,
        since: Optional[int] = None,
    ) -> NxWatchHandle:
        """Poll for changes until ``handle.unsubscribe()`` is called.

        Runs on a daemon thread — safe to use from scripts and services.
        """
        if callback is None:
            raise NxError("watch() needs a callback.", "invalid_input")
        cursor = since if since is not None else 0
        stop = _threading.Event()

        def run() -> None:
            nonlocal cursor
            while not stop.is_set():
                try:
                    res = self.changes(table, cursor)
                    cursor = max(cursor, res["latestSeq"])
                    for event in res["events"]:
                        callback(event)
                except Exception as error:  # noqa: BLE001 — parity with JS: report, keep polling
                    if not stop.is_set():
                        callback({"op": "error", "error": error})
                stop.wait(max(1.0, interval_ms / 1000.0))

        _threading.Thread(target=run, daemon=True).start()
        return NxWatchHandle(stop)


def connect(**options: Any) -> NxDatabase:
    """Connect to an NxDB database. Verifies the connection (advisory)."""
    client = NxDatabase(**options)
    try:
        client.connect_info()
    except Exception:  # advisory — later calls surface auth errors
        pass
    return client
