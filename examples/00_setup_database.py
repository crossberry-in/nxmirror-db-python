"""00 — Provision demo databases (run this FIRST, once)

    python examples/00_setup_database.py            create account + SQL db + NoSQL db
    python examples/00_setup_database.py --cleanup  delete both demo databases again

What it does:
  1. Registers a throwaway NxMirror account (or logs in again on re-runs)
  2. Creates one database with engine "sqlite"  -> SQL + file storage examples
  3. Creates one database with engine "nosql"   -> NoSQL document examples
  4. Writes .env.local with everything the other examples need

This script talks to the account REST API directly (the SDK connects to
*existing* databases; creating accounts/databases is a dashboard-level job).
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BASE = (os_env := __import__("os").environ).get("NX_API_BASE") or "https://nxmirror.netlify.app"
CLEANUP = "--cleanup" in sys.argv


def j(path: str, method: str = "GET", body: dict | None = None, session: str | None = None):
    headers = {"content-type": "application/json"}
    if session:
        headers["authorization"] = f"Bearer {session}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw or "{}")
        except ValueError:
            return e.code, {}


def env_lines(path: Path) -> dict:
    env = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


# ---------------- cleanup mode ----------------
if CLEANUP:
    env = env_lines(ROOT / ".env.local")
    if not env:
        print("No .env.local found — nothing to clean up.")
        sys.exit(0)
    for key, value in env.items():
        os_env.setdefault(key, value)
    session = os_env.get("NX_SESSION")
    if not session and os_env.get("NX_ACCOUNT") and os_env.get("NX_ACCOUNT_PASSWORD"):
        status, data = j("/api/auth/login", "POST", {
            "username": os_env["NX_ACCOUNT"], "password": os_env["NX_ACCOUNT_PASSWORD"],
        })
        session = data.get("token")
        print("re-login OK" if session else f"re-login failed ({status})")
    if not session:
        print("Could not restore a session — delete the two demo databases from the dashboard.")
        sys.exit(1)
    failures = 0
    for label, db_id, db_name in [
        ("sql db  ", os_env.get("NXDB_ID"), os_env.get("NXDB_NAME")),
        ("nosql db", os_env.get("NXDB_NOSQL_ID"), os_env.get("NXDB_NOSQL_NAME")),
    ]:
        if not db_id:
            continue
        status, data = j("/api/db/delete", "DELETE",
                         {"databaseId": db_id, "confirm": db_name or db_id}, session)
        ok = data.get("success") is True
        failures += 0 if ok else 1
        print(f"{'deleted' if ok else 'FAILED'} {label} {db_id} (status {status})")
    if failures == 0:
        (ROOT / ".env.local").unlink()
    print("\nCleanup complete — .env.local removed." if failures == 0
          else f"\n{failures} deletion(s) failed — .env.local kept.")
    sys.exit(1 if failures else 0)

# ---------------- setup mode ----------------
TS = str(int(time.time() * 1000))[-8:]
ACCOUNT = f"dbpy{TS}"
PASSWORD = f"DbPy-{TS}-x9!"
SQL_NAME = f"db-example py sql {TS}"
NOSQL_NAME = f"db-example py nosql {TS}"

# 1. register (fall back to login if the name was taken by an earlier run)
status, data = j("/api/auth/register", "POST", {"username": ACCOUNT, "password": PASSWORD})
session = data.get("token")
if not session:
    status, data = j("/api/auth/login", "POST", {"username": ACCOUNT, "password": PASSWORD})
    session = data.get("token")
    if session:
        print(f"account {ACCOUNT} already existed — logged in")
if not session:
    print(f"register failed ({status}):", data.get("error") or data.get("message") or "unknown error")
    sys.exit(1)
print(f"account ready: {ACCOUNT}")


# 2. create the two demo databases
def create_db(name: str, engine: str) -> dict:
    status, data = j("/api/db/create", "POST",
                     {"name": name, "engine": engine, "description": "db-example demo database"}, session)
    db = (data.get("database") or {})
    pw = ((data.get("credentials") or {}).get("password"))
    if not db.get("id") or not pw:
        print(f"create {engine} failed ({status}):", data.get("error") or data.get("message") or "unknown error")
        sys.exit(1)
    print(f'{engine:<6} database ready: {db["id"]}  ("{name}")')
    return {"id": db["id"], "password": pw, "name": name}


sql_db = create_db(SQL_NAME, "sqlite")
nosql_db = create_db(NOSQL_NAME, "nosql")

# 3. write .env.local
env = "\n".join([
    f"NX_SESSION={session}",
    f"NX_ACCOUNT={ACCOUNT}",
    f"NX_ACCOUNT_PASSWORD={PASSWORD}",
    f"NXDB_NAME={SQL_NAME}",
    f"NXDB_ID={sql_db['id']}",
    f"NXDB_PASSWORD={sql_db['password']}",
    f"NXDB_NOSQL_NAME={NOSQL_NAME}",
    f"NXDB_NOSQL_ID={nosql_db['id']}",
    f"NXDB_NOSQL_PASSWORD={nosql_db['password']}",
    "",
])
(ROOT / ".env.local").write_text(env, encoding="utf-8")

print("""
.env.local written. Now run any example:

  python examples/01_connect.py           # 01 — connect + introspection
  python examples/02_sql_crud.py          # 02 — SQL + query builder
  python examples/03_nosql_crud.py        # 03 — NoSQL document collections
  python examples/04_file_storage.py      # 04 — file storage upload/download
  python examples/05_error_handling.py    # 05 — error handling + wrong_engine guard
  python examples/06_realtime_changes.py  # 06 — changes feed + watch()

When you are finished:  python examples/00_setup_database.py --cleanup
""")
