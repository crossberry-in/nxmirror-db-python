# nxmirror-db (Python) — official SDK for the NxMirror DB platform

[![PyPI](https://img.shields.io/pypi/v/nxmirror-db.svg)](https://pypi.org/project/nxmirror-db/)
[![license](https://img.shields.io/pypi/l/nxmirror-db.svg)](LICENSE)
[![python](https://img.shields.io/pypi/pyversions/nxmirror-db.svg)](https://pypi.org/project/nxmirror-db/)

Complete, production-grade Python client for **[NxMirror DB (NxDB)](https://nxmirror.netlify.app/docs)** —
the cloud SQL (SQLite) database + NoSQL documents + hybrid file storage service.
A faithful port of the official JavaScript SDK
[`nxmirror-db`](https://www.npmjs.com/package/nxmirror-db) with the same wire protocol,
error codes and engine guard.

> தமிழ் வழிகாட்டி: **[README.ta.md](README.ta.md)**

- **Zero dependencies** — Python 3.8+ standard library only
- Synchronous client with safe retries (429 `Retry-After`, GET 5xx, network errors)
- Client-side `wrong_engine` guard (fails fast before any network request)
- Every code path in this repo is executed against the live API before release
  (`scripts/live_e2e.py`: 66 checks).

## Install

```bash
pip install nxmirror-db          # from PyPI (when published)
# or straight from source:
pip install git+https://github.com/crossberry-in/nxmirror-db-python.git
# or from a local clone:
git clone https://github.com/crossberry-in/nxmirror-db-python.git
cd nxmirror-db-python && pip install .
```

Using the platform without installing anything is also fine — copy `.env.example`
to `.env.local` and run the bundled examples (they add the repo root to `sys.path`).

## Quick start

```python
from nxmirror_db import connect

db = connect(database_id="nxdb-…", password="…")     # or databaseId=…

db.exec("CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, body TEXT)")
res = db.query("INSERT INTO notes (body) VALUES (?)", ["hello"])
print(res["lastInsertRowid"])

for row in db.query("SELECT * FROM notes")["rows"]:
    print(row)
```

Two-command demo (creates a throwaway account + 2 databases, runs everything, then cleans up):

```bash
python scripts/live_e2e.py
```

## Examples (mirroring the JS `db-example` repo)

| # | File | What it shows |
| --- | --- | --- |
| 00 | [`examples/00_setup_database.py`](examples/00_setup_database.py) | Create a demo account + one `sqlite` + one `nosql` database, write `.env.local` (`--cleanup` deletes them again) |
| 01 | [`examples/01_connect.py`](examples/01_connect.py) | Connect, `connect_info()`, `details()`, first query |
| 02 | [`examples/02_sql_crud.py`](examples/02_sql_crud.py) | Full SQL: DDL, prepared INSERT, SELECT, JOIN, transaction, query builder |
| 03 | [`examples/03_nosql_crud.py`](examples/03_nosql_crud.py) | NoSQL documents: insert/find/get/update/replace/delete/count/list/drop |
| 04 | [`examples/04_file_storage.py`](examples/04_file_storage.py) | File storage: upload, download, folders, search, public + signed URLs, versions |
| 05 | [`examples/05_error_handling.py`](examples/05_error_handling.py) | `NxError` codes, the `wrong_engine` client-side guard, catch patterns |
| 06 | [`examples/06_realtime_changes.py`](examples/06_realtime_changes.py) | Change feed: `changes()` cursor reads + `watch()` live polling |
| — | [`scripts/live_e2e.py`](scripts/live_e2e.py) | 66-check automated live test (provision → SQL → NoSQL → storage → feed → cleanup) |

Run them:

```bash
python examples/00_setup_database.py     # once — provisions .env.local
python examples/01_connect.py
python examples/02_sql_crud.py
python examples/03_nosql_crud.py
python examples/04_file_storage.py
python examples/05_error_handling.py
python examples/06_realtime_changes.py
python examples/00_setup_database.py --cleanup   # when done
```

## Connecting — the complete picture

```python
from nxmirror_db import NxDatabase, connect

db = NxDatabase(
    databaseId="nxdb-…",         # required
    password="…",                # full access — trusted servers only
    # token="nxdb_…",            # scoped API token (read/write/sql/schema/files/custom:*)
    # appId="nxdbapp-…", appToken="nxdbapp_…",   # embedded apps
    apiBase="https://nxmirror.netlify.app/api",  # override for self-hosted gateways
    timeoutMs=30000,             # per-request timeout
    retries=2,                   # safe retries (0–5)
)
```

Both naming styles work: `databaseId`/`database_id`, `apiBase`/`api_base`,
`appId`/`app_id`, `appToken`/`app_token`, `timeoutMs`/`timeout_ms`.
`connect(**options)` is a convenience wrapper that verifies the connection
(advisory — auth errors surface on the first real call).

| Method | Options | Access | Use where |
| --- | --- | --- | --- |
| Database password | `password` | full access to that database | trusted servers only |
| Scoped API token | `token` | permission set + optional expiry | servers & scripts |
| Application credentials | `appId` + `appToken` | permission set + origin restriction | embedded/browser apps |

Tokens and app secrets are created in the dashboard (`/dashboard/database`) and
returned exactly once. Cross-database access fails with 403 `wrong_database`;
cross-account access returns 404 (existence hidden).

### Introspection

```python
info = db.connect_info()   # { connected, latencyMs, permissions, authMethod, database, sdk: { version, apiBase } }
det = db.details()         # { database, tables[], caller }
```

`connect_info()` also teaches the client the database **engine**, which powers
the `wrong_engine` guard below.

## SQL (engine `sqlite`)

```python
# Parameterized statements — the ONLY safe way to pass user input
res = db.query("INSERT INTO users (username, email) VALUES (?, ?)", ["noxs", "dev@example.com"])
res["rows"]             # array of row dicts
res["changes"]          # rows changed
res["lastInsertRowid"]  # rowid of the last INSERT
res["executionMs"]; res["truncated"]; res["columns"]

# Multi-statement DDL / transactions (no parameters in exec())
db.exec("""
  CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, body TEXT);
  CREATE INDEX IF NOT EXISTS notes_body ON notes(body);
""")
db.exec("BEGIN; UPDATE … ; INSERT … ; COMMIT;")
```

Engine limits: 200 parameters per statement, 64 KB SQL, 1000 rows returned,
`ATTACH`/`DETACH` rejected.

### Query builder

```python
db.table("users").insert({"username": "developer"})
db.table("users").insert([{"username": "a"}, {"username": "b"}])  # batch

rows = (db.table("users")
        .where("score", ">", 10)       # eq ne gt lt gte lte like in
        .where({"active": True})       # object form, AND-combined
        .where_null("deleted_at")
        .order_by("id", "DESC")
        .limit(20).offset(40)
        .select())                     # executes — returns the full result dict
rows["rows"]                           # the data lives in ["rows"]

total = db.table("users").where({"active": True}).count()

db.table("users").update({"username": "noxs"}, {"id": 1})   # SET, WHERE
db.table("users").delete({"id": 1})                          # refuses without a WHERE clause
```

`select()` returns the same shape as `query()`: `{"rows", "columns", "changes",
"executionMs", "truncated", "lastInsertRowid"}`.

## NoSQL (engine `nosql`)

Create the database with **engine `nosql`** (dashboard or `POST /api/db/create`)
— same auth, tokens, storage and change feed as SQL, but a document API:

```python
res = db.nosql.insert("users", {"username": "noxs", "score": 9.5, "profile": {"city": "Chennai"}})
res["lastInsertId"]                     # "d-…"; every doc gets _id/_createdAt/_updatedAt
db.nosql.insert("users", [{...}, {...}])  # batch (200 docs max)

page = db.nosql.find("users", filter={"profile.city": "Chennai"},  # dot-paths into nested objects
                     sort={"score": -1}, limit=20, offset=0,
                     projection=["username", "score"])
page["docs"]; page["total"]

# operators: $eq $ne $gt $gte $lt $lte $in $nin $exists $contains $startsWith + top-level $or
db.nosql.find("users", {"filter": {"$or": [{"tier": "gold"}, {"score": {"$gte": 12}}]}})

db.nosql.get("users", doc_id)                                  # doc dict or None
db.nosql.count("users", {"tier": "gold"})
db.nosql.update("users", doc_id, {"score": 10})                # by id
db.nosql.update("users", {"score": {"$gte": 12}}, {"tier": "gold"}, many=True)
db.nosql.replace("users", doc_id, {"username": "noxs-v2"})     # keeps _id/_createdAt
db.nosql.delete("users", {"score": {"$lt": 5}}, many=True)
db.nosql.list()                                                # collections
db.nosql.drop("scratch")
```

Limits: 256 KB per document, 100 collections / database, 10,000 docs /
collection, 200 docs per batch. Multi-match update/delete **requires**
`many=True` — otherwise HTTP 409 `ambiguous_match`.

## File storage

```python
file = db.storage.upload(
    "images/logo.png",           # folder/filename
    image_bytes,                 # bytes | str (text / data URL / base64) | open file object
    mime="image/png",            # optional (server sniffs) — explicit is safest
    public=True,                 # anonymous GET URL without signature
    # on_progress=lambda p: print(p["pct"], "%"),   # resumable uploads > 3.4 MB
)
file["id"]; file["filename"]; file["mime"]; file["size"]; file["backend"]; file["checksum"]; file["versions"]

db.storage.list(folder="images")
db.storage.from_("images").list()
db.storage.search("logo")

data = db.storage.download(file["id"])          # raw bytes

db.storage.rename(file["id"], filename="logo-v2.png")
db.storage.move(file["id"], "archive")
db.storage.copy(file["id"], folder="backup")
db.storage.mkdir("exports/2026")
db.storage.versions(file["id"])                 # overwrites create new versions
db.storage.signed_url(file["id"], 900)          # private link, 5–60 min TTL
db.storage.delete(file["id"])
```

Public files are also reachable anonymously:
`https://nxmirror.netlify.app/api/db/storage/download/<fileId>?db=<databaseId>`

## Realtime (change polling)

```python
feed = db.changes("users", 0)     # one-shot cursor read → { events, latestSeq }

handle = db.watch("users", lambda event: print(event["seq"], event["op"], event["table"]),
                  interval_ms=5000, since=0)
handle.unsubscribe()
```

`watch()` polls on a daemon thread; it is safe for scripts and services.

## Errors — catch by code

All SDK failures raise `NxError` with a stable `code` and, for server errors,
an HTTP `status`:

```python
from nxmirror_db import NxError

try:
    db.query("SELECT * FROM nope")
except NxError as e:
    print(e.code, e.status, e)     # e.g. sql_error 400 no such table: nope
```

Server codes verified against the live API (`scripts/live_e2e.py`):

| `code` | HTTP | Meaning |
| --- | --- | --- |
| `unauthorized` | 401 | missing credentials (no auth header) |
| `invalid_credentials` | 401 | wrong password/token for that database |
| `wrong_database` | 403 | credentials belong to another database |
| `insufficient_permission` | 403 | token lacks the required permission |
| `forbidden` | 403 | owner-only action from a non-owner |
| `confirm_required` | 400 | destructive action without `confirm` |
| `rate_limited` | 429 | retried automatically per `Retry-After` |
| `sql_error` | 400 | SQLite rejected the statement |
| `wrong_engine` | 400 | SQL vs NoSQL mismatch — raised **client-side** (no `status`) when the engine is already known |
| `ambiguous_match` | 409 | NoSQL filter matched several docs without `many=True` |
| `invalid_collection` | 400 | collection name failed validation |
| `too_large` | 413 | file over the 50 MB resumable limit |
| `request_failed` | — | non-OK response with no structured body |
| `network_error` | — | urllib failed / timeout |
| `invalid_input` | — | bad SDK usage |

## Platform limits

| Limit | Value |
| --- | --- |
| Parameters per statement | 200 |
| SQL size | 64 KB |
| Rows returned | 1000 |
| Single-request upload | 3.5 MB (SDK switches to resumable at 3.4 MB) |
| Resumable upload | 50 MB · 64 parts · 3 MB parts |
| Signed URL TTL | 5–60 minutes |
| Documents | 256 KB · 100 collections · 10,000 docs · 200/batch |
| Backups | last 7 daily backups per database |

## Security best practices

1. **Never** ship the database password to a browser or mobile app bundle — use
   `appId` + `appToken` or short-lived scoped tokens.
2. Give every client the least permission (`read` dashboards, `write`-without-
   `schema` workers).
3. Rotate tokens from the dashboard; credentials are stored hashed server-side.
4. Secrets only ever appear in NxDB auth headers — keep them out of logs.

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `wrong_engine` on `db.query()` | database was created with engine `nosql` — SQL calls need a `sqlite` database |
| `wrong_engine` on `db.nosql.*` | database was created with engine `sqlite` — document calls need a `nosql` database |
| `wrong_database` (403) | credentials are for another database — check `NXDB_ID` in `.env.local` |
| `ambiguous_match` (409) | add `many=True` to the NoSQL update/delete |
| 429 | SDK already honors `Retry-After`; reduce request frequency |
| `ModuleNotFoundError: nxmirror_db` when running examples | run from the repo root, or `pip install -e .` — the bundled examples add the repo root to `sys.path` automatically |
| `network_error` behind a proxy | set `apiBase` to a reachable gateway; the SDK retries GETs twice by default |

## Project structure

```
nxmirror-db-python/
├── nxmirror_db/
│   ├── __init__.py            # public exports
│   ├── errors.py              # NxError + shared upload limits
│   ├── client.py              # NxDatabase: transport, retries, SQL, engine guard, changes/watch
│   ├── query_builder.py       # fluent SQL builder
│   ├── nosql.py               # document collections
│   └── storage.py             # hybrid file storage incl. resumable uploads
├── examples/                  # 00–06 runnable demos (same flow as the JS db-example repo)
├── scripts/live_e2e.py        # 66-check automated live test
├── .env.example               # credential template
├── pyproject.toml             # pip-installable, zero dependencies
└── README.ta.md               # Tamil quick-start guide
```

## Links

- Platform: <https://nxmirror.netlify.app>
- Platform docs: <https://nxmirror.netlify.app/docs>
- JS SDK on npm: <https://www.npmjs.com/package/nxmirror-db>
- JS examples repo: <https://github.com/crossberry-in/db-example>
- SDK source: <https://github.com/crossberry-in/Demoapi> (`packages/nxmirror-db`)
- Tamil guide: [README.ta.md](README.ta.md)

## License

MIT — see [LICENSE](LICENSE).
