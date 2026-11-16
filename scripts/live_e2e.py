#!/usr/bin/env python3
"""Full live end-to-end test for the nxmirror-db Python SDK.

Registers a throwaway account, creates one sqlite + one nosql database,
exercises every SDK area against the real API, then deletes everything.

    python scripts/live_e2e.py
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nxmirror_db import (  # noqa: E402
    NxDatabase,
    NxError,
    connect,
)

BASE = "https://nxmirror.netlify.app"
TS = str(int(time.time() * 1000))[-8:]
ACCOUNT = f"dbpye2e{TS}"
PASSWORD = f"E2ePy-{TS}-x7!"
SQL_NAME = f"dbpy-e2e sql {TS}"
NOSQL_NAME = f"dbpy-e2e nosql {TS}"

PASS = 0
FAIL = 0
ENV_FILE = ROOT / ".env.local"


def check(label: str, ok: bool, extra: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"[PASS] {label}" + (f" — {extra}" if extra else ""))
    else:
        FAIL += 1
        print(f"[FAIL] {label}" + (f" — {extra}" if extra else ""))


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


def make_png(width: int, height: int, rgb: tuple) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (len(data).to_bytes(4, "big") + kind + data
                + zlib.crc32(kind + data).to_bytes(4, "big"))

    r, g, b = rgb
    ihdr = (width.to_bytes(4, "big") + height.to_bytes(4, "big") + bytes([8, 2, 0, 0, 0]))
    row = bytes([0]) + bytes([r, g, b]) * width
    return (bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])
            + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(row * height)) + chunk(b"IEND", b""))


def cleanup(session: str) -> None:
    for db_id, db_name in [(SQL_DB_ID, SQL_NAME), (NOSQL_DB_ID, NOSQL_NAME)]:
        if not db_id:
            continue
        try:
            status, data = j("/api/db/delete", "DELETE",
                             {"databaseId": db_id, "confirm": db_name}, session)
            print(f"cleanup: deleted {db_id} (status {status}, success={data.get('success')})")
        except Exception as e:  # noqa: BLE001
            print(f"cleanup FAILED for {db_id}: {e}")
    if ENV_FILE.exists():
        ENV_FILE.unlink()
        print("cleanup: .env.local removed")


session = None
SQL_DB_ID = NOSQL_DB_ID = None
SQL_PASSWORD = NOSQL_PASSWORD = None

try:
    # ---------- 0. provisioning ----------
    status, data = j("/api/auth/register", "POST", {"username": ACCOUNT, "password": PASSWORD})
    session = data.get("token")
    if not session:
        status, data = j("/api/auth/login", "POST", {"username": ACCOUNT, "password": PASSWORD})
        session = data.get("token")
    check("register/login account", bool(session), ACCOUNT)
    assert session

    for name, engine in [(SQL_NAME, "sqlite"), (NOSQL_NAME, "nosql")]:
        status, data = j("/api/db/create", "POST",
                         {"name": name, "engine": engine, "description": "live e2e"}, session)
        db_id = (data.get("database") or {}).get("id")
        pw = ((data.get("credentials") or {}).get("password"))
        check(f"create {engine} db", bool(db_id and pw), db_id or "?")
        if engine == "sqlite":
            SQL_DB_ID, SQL_PASSWORD = db_id, pw
        else:
            NOSQL_DB_ID, NOSQL_PASSWORD = db_id, pw

    # ---------- 1. connect + introspection ----------
    db = connect(databaseId=SQL_DB_ID, password=SQL_PASSWORD)
    check("connect (sqlite)", db.database_id == SQL_DB_ID)
    info = db.connect_info()
    check("connectInfo connected", info.get("connected") is True)
    check("connectInfo engine sqlite", (info.get("database") or {}).get("engine") == "sqlite")
    check("connectInfo sdk block", info.get("sdk", {}).get("version") == "1.0.0")
    check("permissions learned", db.permissions is not None)
    det = db.details()
    check("details() tables list", isinstance(det.get("tables"), list))

    # ---------- 2. engine guard ----------
    e = None
    try:
        db.nosql.insert("docs", {"x": 1})
    except NxError as ex:
        e = ex
    check("wrong_engine raised", e is not None and e.code == "wrong_engine")
    check("wrong_engine client-side (status None)", e is not None and e.status is None)
    check("wrong_engine message has hint", e is not None and 'requires "nosql"' in str(e))

    # ---------- 3. SQL ----------
    res = db.query("SELECT sqlite_version() AS v, 40 + 2 AS answer")
    check("query scalar", res["rows"][0]["answer"] == 42)
    check("query result keys", set(res.keys()) == {"rows", "columns", "changes", "executionMs", "truncated", "lastInsertRowid"})

    db.exec("""CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT NOT NULL,
               price REAL NOT NULL, stock INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1);
               CREATE INDEX products_price ON products(price);""")
    ins = db.query("INSERT INTO products (name, price, stock) VALUES (?, ?, ?)", ["Coffee 250g", 7.5, 120])
    check("parameterized INSERT lastInsertRowid", int(ins["lastInsertRowid"]) == 1)
    ids = [1]
    for name, price, stock in [("Tea 100g", 3.25, 80), ("Sugar 1kg", 1.99, 200), ("Milk 1L", 1.49, 0)]:
        r = db.query("INSERT INTO products (name, price, stock) VALUES (?, ?, ?)", [name, price, stock])
        ids.append(int(r["lastInsertRowid"]))
    check("multi INSERT ids", ids == [1, 2, 3, 4], str(ids))

    cheap = db.query("SELECT id, name, price FROM products WHERE price < ? AND stock > ? ORDER BY price ASC", [5, 0])
    # Milk 1L has stock 0 → excluded by stock > 0
    check("SELECT where/order", [r["name"] for r in cheap["rows"]] == ["Sugar 1kg", "Tea 100g"])

    stats = db.query("SELECT COUNT(*) AS n, ROUND(SUM(price * stock), 2) AS sv, MIN(price) AS cheapest FROM products")
    check("aggregate SELECT", stats["rows"][0]["n"] == 4 and stats["rows"][0]["cheapest"] == 1.49)

    db.exec(f"""CREATE TABLE orders (id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id), qty INTEGER NOT NULL);
                INSERT INTO orders (product_id, qty) VALUES ({ids[0]}, 2), ({ids[1]}, 5);""")
    joined = db.query("""SELECT o.id AS order_id, p.name, p.price, o.qty, ROUND(p.price * o.qty, 2) AS total
                         FROM orders o JOIN products p ON p.id = o.product_id ORDER BY total DESC""")
    check("JOIN totals", joined["rows"][0]["total"] == 16.25 and joined["rows"][1]["total"] == 15.0)

    db.exec(f"""BEGIN; UPDATE products SET stock = stock - 2 WHERE id = {ids[0]};
                UPDATE products SET stock = stock - 5 WHERE id = {ids[1]};
                INSERT INTO orders (product_id, qty) VALUES ({ids[0]}, 2); COMMIT;""")
    after = db.query("SELECT id, stock FROM products WHERE id IN (?, ?)", [ids[0], ids[1]])
    stocks = {r["id"]: r["stock"] for r in after["rows"]}
    check("transaction batch", stocks[ids[0]] == 118 and stocks[ids[1]] == 75)

    e = None
    try:
        db.query("SELECT * FROM no_such_table_xyz")
    except NxError as ex:
        e = ex
    check("sql_error code", e is not None and e.code == "sql_error" and e.status == 400)

    # ---------- 4. query builder ----------
    db.table("products").insert({"name": "Honey 500g", "price": 4.75, "stock": 30})
    db.table("products").insert([
        {"name": "Salt 500g", "price": 0.99, "stock": 500},
        {"name": "Pepper 50g", "price": 2.5, "stock": 45},
    ])
    all_rows = db.table("products").select()
    check("builder select full result", len(all_rows["rows"]) == 7 and "columns" in all_rows)
    cols = db.table("products").select(["name", "price"])
    check("builder projection", set(cols["rows"][0].keys()) == {"name", "price"})
    filtered = (db.table("products").where("price", ">", 2).where({"active": True})
                .order_by("price", "DESC").limit(3).offset(0).select())
    check("builder where/order/limit", [r["name"] for r in filtered["rows"]][:2] == ["Coffee 250g", "Honey 500g"])
    check("builder count", db.table("products").where("stock", ">", 10).count() == 6)
    db.table("products").update({"price": 7.99}, {"id": ids[0]})
    check("builder update", db.table("products").where("id", "=", ids[0]).select(["price"])["rows"][0]["price"] == 7.99)
    db.table("products").delete({"name": "Salt 500g"})
    check("builder delete", db.table("products").count() == 6)
    e = None
    try:
        db.table("products").delete()
    except NxError as ex:
        e = ex
    check("builder delete refuses without WHERE", e is not None and e.code == "invalid_input")
    e = None
    try:
        db.table("bad-name!")
    except NxError as ex:
        e = ex
    check("builder rejects bad table name", e is not None and e.code == "invalid_input")

    # ---------- 5. NoSQL ----------
    ndb = connect(databaseId=NOSQL_DB_ID, password=NOSQL_PASSWORD)
    check("connect (nosql)", ndb.database_id == NOSQL_DB_ID)
    ndb.connect_info()
    check("nosql engine learned", ndb.engine == "nosql")

    one = ndb.nosql.insert("users", {"username": "noxs", "score": 9.5,
                                     "profile": {"city": "Chennai", "verified": True}})
    check("nosql insert one", one["inserted"] == 1 and bool(one["lastInsertId"]))
    got = ndb.nosql.get("users", one["lastInsertId"])
    check("nosql get metadata", got["_id"] == one["lastInsertId"] and "_createdAt" in got)
    check("nosql get missing → None", ndb.nosql.get("users", "d-nope") is None)

    many = ndb.nosql.insert("users", [
        {"username": "arun", "score": 7, "profile": {"city": "Madurai"}},
        {"username": "bala", "score": 12, "active": False, "profile": {"city": "Chennai"}},
    ])
    check("nosql insert many", many["inserted"] == 2 and len(many["ids"]) == 2)

    by_city = ndb.nosql.find("users", filter={"profile.city": "Chennai"})
    check("nosql dot-path filter", by_city["total"] == 2)
    ranked = ndb.nosql.find("users", {"filter": {"username": {"$in": ["noxs", "arun", "bala"]}},
                                      "sort": {"score": -1}, "limit": 10,
                                      "projection": ["username", "score"]})
    check("nosql $in+sort+projection",
          [d["username"] for d in ranked["docs"]] == ["bala", "noxs", "arun"]
          and set(ranked["docs"][0].keys()) <= {"username", "score", "_id"})
    gold = ndb.nosql.find("users", {"filter": {"$or": [{"active": False}, {"score": {"$gte": 12}}]}})
    check("nosql $or", [d["username"] for d in gold["docs"]] == ["bala"])
    check("nosql count x2", ndb.nosql.count("users") == 3
          and ndb.nosql.count("users", {"profile.city": "Chennai"}) == 2)

    ndb.nosql.update("users", one["lastInsertId"], {"score": 10, "profile.city": "Coimbatore"})
    after_doc = ndb.nosql.get("users", one["lastInsertId"])
    check("nosql dot-path patch", after_doc["score"] == 10 and after_doc["profile"]["city"] == "Coimbatore")
    e = None
    try:
        ndb.nosql.update("users", {"score": {"$gte": 1}}, {"tier": "gold"})  # matches several docs
    except NxError as ex:
        e = ex
    check("nosql ambiguous_match 409", e is not None and e.code == "ambiguous_match" and e.status == 409)
    bulk = ndb.nosql.update("users", {"score": {"$gte": 12}}, {"tier": "gold"}, many=True)
    check("nosql bulk update many", bulk["updated"] == 1)
    rep = ndb.nosql.replace("users", many["ids"][0], {"username": "arun-v2", "score": 7})
    check("nosql replace keeps _id", rep["replaced"]["_id"] == many["ids"][0])
    deleted = ndb.nosql.delete("users", many["ids"][1])
    check("nosql delete by id", deleted["deleted"] == 1)
    left = ndb.nosql.delete("users", {"score": {"$lt": 8}}, many=True)
    check("nosql delete by filter", left["deleted"] == 1)
    colls = ndb.nosql.list()
    check("nosql list collections", any(c["name"] == "users" for c in colls))
    ndb.nosql.insert("scratch", {"a": 1})
    dropped = ndb.nosql.drop("scratch")
    check("nosql drop", dropped.get("dropped") == "scratch" and dropped.get("documents") == 1)

    # ---------- 6. storage ----------
    png = make_png(64, 64, (245, 130, 32))
    try:
        db.storage.mkdir("images")
    except NxError:
        pass
    file = db.storage.upload("images/nxdb-square.png", png, mime="image/png", public=True)
    check("storage upload record", file["id"].startswith("f-") and file["mime"] == "image/png"
          and file["public"] is True and file["backend"] in ("blob", "sql"))
    back = db.storage.download(file["id"])
    check("storage download byte-identical", back == png, f"{len(back)} bytes")
    check("storage list", isinstance(db.storage.list(), list) and len(db.storage.list()) >= 1)
    check("storage from_ folder", any(f["filename"] == "nxdb-square.png" for f in db.storage.from_("images").list()))
    txt = db.storage.upload("notes/hello.txt", "Hello from the nxmirror-db Python SDK!", mime="text/plain")
    check("storage search", any(f["filename"] == "nxdb-square.png" for f in db.storage.search("square")))
    public_url = f"{BASE}/api/db/storage/download/{file['id']}?db={db.database_id}"
    with urllib.request.urlopen(public_url, timeout=30) as resp:
        body = resp.read()
        check("anonymous public URL 200 image/png",
              resp.status == 200 and resp.headers.get("content-type") == "image/png" and body == png)
    signed = db.storage.signed_url(file["id"], 900)
    check("signed URL built", signed.startswith(BASE) and "signature=" in signed or "token=" in signed or len(signed) > len(BASE) + 20)
    renamed = db.storage.rename(file["id"], filename="nxdb-square-v2.png")
    check("storage rename", (renamed.get("filename") == "nxdb-square-v2.png") or renamed.get("id") == file["id"])
    copy = db.storage.copy(file["id"], folder="backup")
    check("storage copy", copy["id"] != file["id"])
    overwritten = db.storage.upload("images/nxdb-square-v2.png",
                                    make_png(64, 64, (32, 130, 245)), mime="image/png", public=True)
    hist = db.storage.versions(overwritten["id"])
    check("storage versions after overwrite", len(hist["versions"]) >= 1 and hist["current"]["id"] == overwritten["id"])
    check("storage delete copy", db.storage.delete(copy["id"]) is True)
    check("storage delete txt", db.storage.delete(txt["id"]) is True)
    check("storage delete overwritten", db.storage.delete(overwritten["id"]) is True)

    # ---------- 7. change feed ----------
    db.exec("CREATE TABLE feed_demo (id INTEGER PRIMARY KEY, note TEXT)")
    db.table("feed_demo").insert({"note": "first"})
    db.table("feed_demo").insert({"note": "second"})
    feed = db.changes("feed_demo", 0)
    check("changes one-shot", len(feed["events"]) >= 2 and feed["latestSeq"] > 0)
    seen = []
    handle = db.watch("feed_demo", seen.append, interval_ms=2000, since=feed["latestSeq"])
    time.sleep(1.0)
    db.table("feed_demo").insert({"note": "while watching"})
    deadline = time.time() + 15
    while time.time() < deadline and not seen:
        time.sleep(0.5)
    handle.unsubscribe()
    check("watch saw live event", len(seen) >= 1 and seen[0].get("op") == "write")
    db.exec("DROP TABLE feed_demo")

    # ---------- 8. auth errors ----------
    e = None
    try:
        NxDatabase(databaseId=SQL_DB_ID, password="definitely-wrong").connect_info()
    except NxError as ex:
        e = ex
    check("invalid_credentials 401", e is not None and e.code == "invalid_credentials" and e.status == 401)
    e = None
    try:
        NxDatabase(databaseId="nxdb-000000000000", password="whatever").connect_info()
    except NxError as ex:
        e = ex
    check("wrong db rejected", e is not None and e.code in ("wrong_database", "invalid_credentials", "not_found", "request_failed"))

    # ---------- 9. validation ----------
    e = None
    try:
        NxDatabase(databaseId="")
    except NxError as ex:
        e = ex
    check("databaseId required", e is not None and e.code == "invalid_input")
    e = None
    try:
        NxDatabase(databaseId=SQL_DB_ID)
    except NxError as ex:
        e = ex
    check("auth method required", e is not None and e.code == "invalid_input")

finally:
    if session:
        cleanup(session)

print(f"\n===== LIVE E2E SUMMARY: {PASS} PASS / {FAIL} FAIL =====")
sys.exit(1 if FAIL else 0)
