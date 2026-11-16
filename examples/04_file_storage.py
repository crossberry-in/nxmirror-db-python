"""04 — Hybrid file storage: upload, download, folders, URLs, versions

    python examples/04_file_storage.py

Small files are stored as SQL BLOBs, larger ones in object storage — the SDK
picks the backend automatically and switches to resumable part uploads above
3.4 MB (up to 50 MB). Overwrites create new versions; every file gets a
SHA-256 checksum.

This example generates its own PNG in-memory, so it needs no downloads.
"""
import urllib.request
import zlib

from config import sql_creds, API_BASE, banner  # also puts the repo root on sys.path
from nxmirror_db import connect


# ---------- tiny self-contained PNG generator ----------
def make_png(width: int, height: int, rgb: tuple) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (len(data).to_bytes(4, "big") + kind + data
                + zlib.crc32(kind + data).to_bytes(4, "big"))

    r, g, b = rgb
    ihdr = (width.to_bytes(4, "big") + height.to_bytes(4, "big")
            + bytes([8, 2, 0, 0, 0]))  # bit depth 8, truecolor RGB
    row = bytes([0]) + bytes([r, g, b]) * width  # 1 filter byte (0) per row
    raw = row * height
    return (bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])  # PNG signature
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


db = connect(**sql_creds())
png = make_png(64, 64, (245, 130, 32))  # NxMirror orange square
print(f"generated png: {len(png)} bytes")

# ---------- 1. folders + upload ----------
banner("storage.mkdir + storage.upload")
try:
    db.storage.mkdir("images")
except Exception:
    pass  # already exists → fine

file = db.storage.upload(
    "images/nxdb-square.png",
    png,                       # bytes | str | open file object
    mime="image/png",          # optional — server sniffs it; explicit is safest
    public=True,               # anonymous GET URL without a signature
)
print("uploaded file record:", {
    "id": file["id"],
    "filename": file["filename"],
    "mime": file["mime"],
    "size": file["size"],
    "backend": file["backend"],   # blob/sql — chosen automatically
    "folder": file["folder"],
    "checksum": str(file["checksum"])[:16] + "…",
    "public": file["public"],
    "versions": file["versions"],
})

# ---------- 2. download back and byte-compare ----------
banner("storage.download()")
back = db.storage.download(file["id"])
print("byte-identical:", back == png, f"({len(back)} bytes)")

# ---------- 3. list / folder views / search ----------
banner("storage.list / from_ / search")
print("total files:", len(db.storage.list()))
print("in images/:", [f["filename"] for f in db.storage.from_("images").list()])

# a plain text upload via string content
txt = db.storage.upload("notes/hello.txt",
                        "Hello from the nxmirror-db Python SDK!",
                        mime="text/plain")
print("search('square'):", [f["filename"] for f in db.storage.search("square")])

# ---------- 4. public URL (no auth) + signed URL (private files) ----------
banner("URLs")
public_url = f"{API_BASE}/api/db/storage/download/{file['id']}?db={db.database_id}"
with urllib.request.urlopen(public_url, timeout=30) as resp:
    print("public URL :", public_url)
    print("  status:", resp.status, "| content-type:", resp.headers.get("content-type"))
# private files: url = db.storage.signed_url(file["id"], 900)  # 5–60 min TTL
signed = db.storage.signed_url(file["id"], 900)
print("signed URL :", signed[:72] + "…")

# ---------- 5. rename / copy / versions / delete ----------
banner("rename / copy / versions / delete")
renamed = db.storage.rename(file["id"], filename="nxdb-square-v2.png")
print("renamed to:", renamed.get("filename") or "nxdb-square-v2.png")

copy = db.storage.copy(file["id"], folder="backup")
print("copied to backup/:", copy["filename"], "(id", copy["id"] + ")")

overwritten = db.storage.upload(
    "images/nxdb-square-v2.png",
    make_png(64, 64, (32, 130, 245)),  # same path, new content → new version
    mime="image/png",
    public=True,
)
hist = db.storage.versions(overwritten["id"])
print("current version:", hist["current"]["id"], "| history entries:", len(hist["versions"]))

db.storage.delete(copy["id"])
print("backup copy deleted")

db.storage.delete(txt["id"])
db.storage.delete(overwritten["id"])
print("\nOK — storage demo finished (demo files removed).")
