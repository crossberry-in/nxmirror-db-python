"""03 — NoSQL document collections (engine "nosql" database)

    python examples/03_nosql_crud.py

IMPORTANT: db.nosql.* needs a database created with engine "nosql"
(dashboard, or `python examples/00_setup_database.py` which makes one for you).
Calling it on a sqlite database throws a client-side wrong_engine error —
see 05_error_handling.py.
"""
from config import nosql_creds, banner  # also puts the repo root on sys.path
from nxmirror_db import connect

db = connect(**nosql_creds())

# ---------- 1. insert one / many ----------
banner("nosql.insert()")
one = db.nosql.insert("users", {
    "username": "noxs",
    "score": 9.5,
    "tags": ["pro"],
    "profile": {"city": "Chennai", "verified": True},
})
print("inserted:", one["inserted"], "id:", one["lastInsertId"])

many = db.nosql.insert("users", [
    {"username": "arun", "score": 7, "profile": {"city": "Madurai"}},
    {"username": "bala", "score": 12, "active": False, "profile": {"city": "Chennai"}},
])
print("inserted many:", many["inserted"], "ids:", ", ".join(many["ids"]))

# Every document gets immutable metadata: _id, _createdAt, _updatedAt
got = db.nosql.get("users", one["lastInsertId"])
banner("nosql.get()")
print(got)

# ---------- 2. find() with filters ----------
banner("nosql.find() — dot-path into nested objects")
by_city = db.nosql.find("users", filter={"profile.city": "Chennai"})
print("total:", by_city["total"], "names:", ", ".join(d["username"] for d in by_city["docs"]))

banner("nosql.find() — $in + sort")
ranked = db.nosql.find("users", {
    "filter": {"username": {"$in": ["noxs", "arun", "bala"]}},
    "sort": {"score": -1},  # descending; {"score": 1} would be ascending
    "limit": 10,
    "projection": ["username", "score"],
})
for doc in ranked["docs"]:
    print(doc)

banner("nosql.find() — $or + operators")
# Operators: $eq $ne $gt $gte $lt $lte $in $nin $exists $contains $startsWith, top-level $or
gold = db.nosql.find("users", {"filter": {"$or": [{"active": False}, {"score": {"$gte": 12}}]}})
print("matched:", ", ".join(d["username"] for d in gold["docs"]))

banner("nosql.count()")
print("all:", db.nosql.count("users"),
      "| Chennai:", db.nosql.count("users", {"profile.city": "Chennai"}))

# ---------- 3. update / replace ----------
banner("nosql.update()")
db.nosql.update("users", one["lastInsertId"], {"score": 10, "profile.city": "Coimbatore"})
after = db.nosql.get("users", one["lastInsertId"])
print("patched:", {"score": after["score"], "city": after["profile"]["city"]})

# Multi-match updates REQUIRE many=True (otherwise 409 ambiguous_match)
bulk = db.nosql.update("users", {"score": {"$gte": 12}}, {"tier": "gold"}, many=True)
print("bulk update matched:", bulk["updated"])

banner("nosql.replace()")
rep = db.nosql.replace("users", many["ids"][0], {"username": "arun-v2", "score": 7})
print("kept _id:", rep["replaced"]["_id"] == many["ids"][0], "name:", rep["replaced"]["username"])

# ---------- 4. delete / list / drop ----------
banner("nosql.delete() + list() + drop()")
deleted = db.nosql.delete("users", many["ids"][1])
print("deleted by id:", deleted["deleted"])

left = db.nosql.delete("users", {"score": {"$lt": 8}}, many=True)
print("deleted by filter:", left["deleted"])

print("collections:", db.nosql.list())

# collections are created on first insert — drop() removes the whole collection
db.nosql.insert("scratch", {"a": 1})
dropped = db.nosql.drop("scratch")
print("dropped:", dropped["dropped"], "(had", dropped["documents"], "documents)")

print("\nOK — NoSQL demo finished.")
