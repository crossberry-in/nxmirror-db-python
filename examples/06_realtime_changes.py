"""06 — Realtime: change feed polling with changes() and watch()

    python examples/06_realtime_changes.py

Every mutation writes change-feed rows server-side. changes() reads them
once (cursor-based), watch() keeps polling at a safe interval until you
unsubscribe. (WebSocket push is planned — polling is the reliable transport
available on this infrastructure today.)
"""
import time

from config import sql_creds, banner   # also puts the repo root on sys.path
from nxmirror_db import connect

db = connect(**sql_creds())

db.exec("CREATE TABLE IF NOT EXISTS feed_demo (id INTEGER PRIMARY KEY, note TEXT)")
db.query("DELETE FROM feed_demo")  # start empty

# ---------- 1. one-shot cursor read: db.changes(table, since) ----------
banner("changes() — one-shot read")
db.table("feed_demo").insert({"note": "first"})
db.table("feed_demo").insert({"note": "second"})

res = db.changes("feed_demo", 0)  # since = cursor 0
events, latest_seq = res["events"], res["latestSeq"]
print("latestSeq:", latest_seq)
for ev in events:
    print(f"  seq={ev['seq']} op={ev['op']} table={ev['table']}")

# ---------- 2. continuous watch() with unsubscribe ----------
banner("watch() — live polling for ~12 s")
seen = 0

def on_event(event):
    global seen
    seen += 1
    print(f"  [watch] seq={event['seq']} op={event['op']} table={event['table']}")

handle = db.watch("feed_demo", on_event, interval_ms=5000, since=latest_seq)

# generate activity while the watcher polls
time.sleep(1.0)
db.table("feed_demo").insert({"note": "while watching #1"})
time.sleep(2.0)
db.table("feed_demo").insert({"note": "while watching #2"})
time.sleep(3.0)
db.table("feed_demo").update({"note": "edited!"}, {"note": "while watching #1"})
time.sleep(6.0)

handle.unsubscribe()
print("unsubscribed. events seen by watch():", seen)

# ---------- 3. cleanup ----------
db.exec("DROP TABLE IF EXISTS feed_demo")
print("\nOK — realtime demo finished.")
