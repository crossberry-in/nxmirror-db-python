"""01 — Connect and introspect

    python examples/01_connect.py

Shows the standard connection flow used by every other example:
connect -> connectInfo -> details -> first query.
"""
from config import sql_creds, banner   # also puts the repo root on sys.path
from nxmirror_db import connect

# 1. connect — full-access database password (server-side code only!)
#    Alternatives: {"databaseId": ..., "token": ...}  or  appId + appToken
db = connect(**sql_creds())
print("connected:", db.database_id)

# 2. connectInfo() — who am I, how fast, which engine, which SDK?
info = db.connect_info()
banner("connect_info()")
print({
    "connected": info.get("connected"),
    "latencyMs": info.get("latencyMs"),
    "authMethod": info.get("authMethod"),
    "permissions": info.get("permissions"),
    "engine": (info.get("database") or {}).get("engine"),
    "database": (info.get("database") or {}).get("name"),
    "sdk": info.get("sdk"),
})

# 3. details() — database metadata + current table list
det = db.details()
banner("details()")
tables = det.get("tables") or []
print("tables:", ", ".join(t.get("name", t) if isinstance(t, dict) else str(t) for t in tables) or "(none yet)")

# 4. first query — scalar expression, no tables needed
r = db.query("SELECT sqlite_version() AS sqlite_version, 40 + 2 AS answer")
banner("first query")
for row in r["rows"]:
    print(row)
print("result keys:", ", ".join(r.keys()))

print("\nOK — Python connect works. Next: python examples/02_sql_crud.py")
