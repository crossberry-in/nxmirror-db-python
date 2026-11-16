"""05 — Error handling: NxError, error codes, the wrong_engine guard

    python examples/05_error_handling.py

Every SDK failure raises NxError with a stable ``code`` and (for server
errors) an HTTP ``status``. Catch them by code — never by parsing messages.
"""
from config import sql_creds, nosql_creds, banner  # also puts the repo root on sys.path
from nxmirror_db import NxDatabase, NxError, connect


def catch_error(fn):
    """runs fn, returns the raised NxError (or None)"""
    try:
        fn()
        return None
    except NxError as e:
        return e


# ---------- 1. invalid_credentials (401) — wrong password ----------
banner("401 invalid_credentials")
creds = sql_creds()
e1 = catch_error(lambda: NxDatabase(databaseId=creds["databaseId"], password="definitely-wrong").connect_info())
print({"name": type(e1).__name__ if e1 else None,   # NxError
       "code": e1.code if e1 else None,             # "invalid_credentials"
       "status": e1.status if e1 else None})        # 401

# ---------- 2. sql_error (400) — SQLite rejected the statement ----------
banner("400 sql_error")
db = connect(**sql_creds())
e2 = catch_error(lambda: db.query("SELECT * FROM table_that_does_not_exist"))
print({"code": e2.code if e2 else None, "status": e2.status if e2 else None,
       "message": (str(e2) if e2 else "")[:60] + "…"})

# ---------- 3. wrong_engine — CLIENT-SIDE guard, no network round-trip ----------
banner("wrong_engine guard (sqlite db, db.nosql.* call)")
# From SDK 1.1.1 the SDK knows each database's engine after connectInfo() and
# fails fast BEFORE sending anything. Note e3.status is None:
e3 = catch_error(lambda: db.nosql.insert("docs", {"hello": "world"}))
print({"code": e3.code if e3 else None, "status": e3.status if e3 else None,
       "clientSide": e3.status is None if e3 else None})
print("hint:", " ".join(str(e3).split()[-14:]) if e3 else None)
# (the hint is part of the message — no network request was made)

# ---------- 4. ambiguous_match (409) — NoSQL multi-match without many=True ----------
banner("409 ambiguous_match (nosql db)")
ndb = connect(**nosql_creds())
ndb.nosql.insert("demo", [{"n": 1, "tier": "bronze"}, {"n": 2, "tier": "bronze"}])
e4 = catch_error(lambda: ndb.nosql.update("demo", {"tier": "bronze"}, {"tier": "gold"}))
print({"code": e4.code if e4 else None, "status": e4.status if e4 else None})  # many=True would fix this
ndb.nosql.update("demo", {"tier": "bronze"}, {"tier": "gold"}, many=True)
ndb.nosql.drop("demo")

# ---------- 5. the universal catch pattern ----------
banner("recommended pattern")
try:
    db.query("SELECT * FROM products")
except NxError as e:
    if e.code in ("unauthorized", "invalid_credentials"):
        print("check credentials")
    elif e.code == "wrong_database":
        print("credentials belong to another database")
    elif e.code == "insufficient_permission":
        print("token lacks this permission")
    elif e.code == "wrong_engine":
        print("SQL vs NoSQL mismatch — see README")
    elif e.code == "rate_limited":
        print("slow down (retries already honored)")
    elif e.code == "sql_error":
        print("fix the SQL:", e)
    else:
        print("unhandled:", e.code, e)

print("\nFull code table: README.md → Errors.")
print("OK — error handling demo finished.")
