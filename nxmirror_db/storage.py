"""Hybrid file storage (official Python SDK port).

Small files are stored as SQL BLOBs, larger ones in object storage — the SDK
picks the backend automatically and switches to resumable part uploads above
3.4 MB (up to 50 MB). Overwrites create new versions; every file gets a
SHA-256 checksum.
"""
from __future__ import annotations

import base64 as _base64
import re as _re
import urllib.parse as _urlparse
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

from .errors import NxError, RESUMABLE_MAX_TOTAL, RESUMABLE_PART_SIZE, SINGLE_UPLOAD_MAX

if TYPE_CHECKING:  # pragma: no cover — typing only, avoids a circular import
    from .client import NxDatabase

_DATA_URL_RE = _re.compile(r"^data:[^;]+;base64,")
_B64_RE = _re.compile(r"^[A-Za-z0-9+/]+={0,2}$")


def _to_bytes(content: Any) -> bytes:
    """Port of the JS ``toBytes`` helper: str (text/data-URL/base64), bytes, file-like."""
    if content is None:
        raise NxError("No file content provided for upload.", "invalid_input")
    if isinstance(content, str):
        text = content
        match = _DATA_URL_RE.match(text)
        if match:
            text = text[match.end():]
        stripped = _re.sub(r"\s+", "", text)
        if _B64_RE.fullmatch(stripped) and len(stripped) % 4 == 0:
            try:
                return _base64.b64decode(stripped, validate=True)
            except Exception:  # noqa: BLE001 — looked like base64 but wasn't; treat as text
                pass
        return text.encode("utf-8")
    if isinstance(content, (bytes, bytearray, memoryview)):
        return bytes(content)
    read = getattr(content, "read", None)
    if callable(read):
        data = read()
        if isinstance(data, str):
            return data.encode("utf-8")
        return bytes(data)
    raise NxError(
        "Unsupported file content type. Pass bytes, a str, or an open file object.",
        "invalid_input",
    )


def _clean(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Drop keys whose value is None (parity with JS: undefined keys are omitted from JSON)."""
    return {k: v for k, v in payload.items() if v is not None}


class _NxFolderScope:
    """Folder-scoped view: ``db.storage.from_("images").list()``."""

    def __init__(self, storage: "NxStorage", folder: str):
        self._storage = storage
        self._folder = folder

    def list(self, q: Optional[str] = None):
        return self._storage.list(folder=self._folder, q=q)


class NxStorage:
    """File storage namespace: ``db.storage.upload(...)``, ``db.storage.download(...)`` ..."""

    def __init__(self, client: "NxDatabase"):
        self.client = client

    def from_(self, folder: str) -> _NxFolderScope:
        """Choose a folder scope (JS parity: ``storage.from(folder).list()``)."""
        return _NxFolderScope(self, folder)

    def list(self, folder: str = "", q: Optional[str] = None):
        params: Dict[str, str] = {"db": self.client.database_id}
        if folder:
            params["folder"] = folder
        if q:
            params["q"] = q
        result = self.client.request("storage/list?" + _urlparse.urlencode(params))
        return result.get("files") or []

    def search(self, q: str):
        return self.list(q=q)

    def upload(
        self,
        path: str,
        file: Any,
        mime: Optional[str] = None,
        public: Optional[bool] = None,
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """Upload a file.

        ``file`` accepts ``bytes``/``bytearray``, a ``str`` (plain text, a data
        URL, or raw base64), or an open file object. ``path`` is
        ``"folder/filename"``. Returns the file record dict.
        """
        if not path or not str(path).strip():
            raise NxError("upload() needs a path like 'images/logo.png'.", "invalid_input")
        clean = [part for part in str(path).replace("\\", "/").split("/") if part]
        filename = clean.pop()
        folder = "/".join(clean)
        data = _to_bytes(file)

        if len(data) > SINGLE_UPLOAD_MAX:
            if len(data) > RESUMABLE_MAX_TOTAL:
                raise NxError(f"Files are limited to {RESUMABLE_MAX_TOTAL // (1024 * 1024)} MB.", "too_large", 413)
            init = self.client.request(
                "storage/upload/init",
                method="POST",
                body=_clean(
                    {
                        "databaseId": self.client.database_id,
                        "filename": filename,
                        "folder": folder,
                        "mime": mime,
                        "size": len(data),
                        "partSize": RESUMABLE_PART_SIZE,
                    }
                ),
            )
            part_count = int(init["partCount"])
            for index in range(part_count):
                chunk = data[index * RESUMABLE_PART_SIZE : (index + 1) * RESUMABLE_PART_SIZE]
                self.client.request(
                    "storage/upload/part",
                    method="PUT",
                    body={
                        "databaseId": self.client.database_id,
                        "uploadId": init["uploadId"],
                        "index": index,
                        "content": _base64.b64encode(chunk).decode("ascii"),
                    },
                )
                if on_progress:
                    on_progress(
                        {
                            "loaded": min(len(data), (index + 1) * RESUMABLE_PART_SIZE),
                            "total": len(data),
                            "pct": min(99, round((index + 1) / part_count * 99)),
                            "part": index + 1,
                            "parts": part_count,
                        }
                    )
            completed = self.client.request(
                "storage/upload/complete",
                method="POST",
                body=_clean(
                    {
                        "databaseId": self.client.database_id,
                        "uploadId": init["uploadId"],
                        "public": public,
                    }
                ),
            )
            if on_progress:
                on_progress({"loaded": len(data), "total": len(data), "pct": 100})
            return completed["file"]

        result = self.client.request(
            "storage/upload",
            method="POST",
            body=_clean(
                {
                    "databaseId": self.client.database_id,
                    "filename": filename,
                    "folder": folder,
                    "mime": mime,
                    "content": _base64.b64encode(data).decode("ascii"),
                    "public": public,
                }
            ),
        )
        if on_progress:
            on_progress({"loaded": len(data), "total": len(data), "pct": 100})
        return result["file"]

    def download(self, file_id: str) -> bytes:
        """Download a file. Returns raw bytes."""
        url = f"storage/download/{_urlparse.quote(str(file_id), safe='')}?db={_urlparse.quote(self.client.database_id, safe='')}"
        return self.client.request(url, blob=True)

    def signed_url(self, file_id: str, ttl_seconds: int = 900) -> str:
        """Short-lived signed URL for private files (default 15 minutes; 5–60 min TTL)."""
        result = self.client.request(
            "storage/signed",
            method="POST",
            body={"databaseId": self.client.database_id, "id": file_id, "ttlSeconds": ttl_seconds},
        )
        base = _re.sub(r"/api$", "", self.client.api_base)
        return base + result["url"]

    # camelCase alias
    signedUrl = signed_url

    def rename(self, file_id: str, filename: Optional[str] = None, folder: Optional[str] = None) -> Dict[str, Any]:
        result = self.client.request(
            "storage/update",
            method="POST",
            body=_clean(
                {
                    "databaseId": self.client.database_id,
                    "id": file_id,
                    "filename": filename,
                    "folder": folder,
                }
            ),
        )
        return result["file"]

    def move(self, file_id: str, folder: str) -> Dict[str, Any]:
        return self.rename(file_id, folder=folder)

    def copy(self, file_id: str, filename: Optional[str] = None, folder: Optional[str] = None) -> Dict[str, Any]:
        result = self.client.request(
            "storage/copy",
            method="POST",
            body=_clean(
                {
                    "databaseId": self.client.database_id,
                    "id": file_id,
                    "filename": filename,
                    "folder": folder,
                }
            ),
        )
        return result["file"]

    def mkdir(self, path: str) -> Dict[str, Any]:
        return self.client.request(
            "storage/folders",
            method="POST",
            body={"databaseId": self.client.database_id, "path": path},
        )

    def delete(self, file_id: str) -> bool:
        self.client.request(
            "storage/delete",
            method="POST",
            body={"databaseId": self.client.database_id, "id": file_id},
        )
        return True

    def versions(self, file_id: str) -> Dict[str, Any]:
        """Version history: ``{current, versions}`` — overwrites create new versions."""
        url = f"storage/versions/{_urlparse.quote(str(file_id), safe='')}?db={_urlparse.quote(self.client.database_id, safe='')}"
        result = self.client.request(url)
        return {"current": result.get("current"), "versions": result.get("versions") or []}


def _clean(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Drop keys whose value is None (parity with JS: undefined keys are omitted from JSON)."""
    return {k: v for k, v in payload.items() if v is not None}
