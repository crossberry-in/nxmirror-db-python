"""NoSQL document collections for databases created with engine ``nosql``.

Filter syntax (AND across keys, dot-paths into nested objects)::

    {"field": value}                 exact match
    {"field": {"$gt": 10}}           $eq $ne $gt $gte $lt $lte $in $nin $exists $contains $startsWith
    {"$or": [{...}, {...}]}          top-level OR
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from .errors import NxError

if TYPE_CHECKING:  # pragma: no cover — typing only, avoids a circular import
    from .client import NxDatabase


def _clean(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Drop keys whose value is None (parity with JS: undefined keys are omitted from JSON)."""
    return {k: v for k, v in payload.items() if v is not None}


class NxNoSql:
    """Document API namespace: ``db.nosql.insert(...)``, ``db.nosql.find(...)`` ..."""

    def __init__(self, client: "NxDatabase"):
        self.client = client

    def _op(self, op: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.client._assert_engine("nosql")
        return self.client.request(
            f"nosql/{op}",
            method="POST",
            body={"databaseId": self.client.database_id, **payload},
        )

    def insert(self, collection: str, doc_or_docs: Union[Dict[str, Any], List[Dict[str, Any]]]) -> Dict[str, Any]:
        """Insert one document or a list of documents. Returns ``{inserted, ids, lastInsertId}``."""
        payload: Dict[str, Any] = {"docs": doc_or_docs} if isinstance(doc_or_docs, list) else {"doc": doc_or_docs}
        return self._op("insert", {"collection": collection, **payload})

    def find(
        self,
        collection: str,
        options: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Query documents: ``filter``/``projection``/``sort``/``limit``/``offset``.

        Returns ``{docs, total, truncated}``. Accepts either a JS-style options
        dict (``find("users", {"filter": {...}})``) or keyword arguments
        (``find("users", filter={...}, limit=20)``).
        """
        merged: Dict[str, Any] = {**(options or {}), **kwargs}
        return self._op("find", _clean({"collection": collection, **merged}))

    def get(self, collection: str, id: str) -> Optional[Dict[str, Any]]:
        """Fetch one document by ``_id`` (None when missing)."""
        try:
            return self._op("get", {"collection": collection, "id": id}).get("doc")
        except NxError as error:
            if error.status == 404:
                return None
            raise

    def count(self, collection: str, filter: Optional[Dict[str, Any]] = None) -> int:
        """Count documents matching a filter."""
        return int(self._op("count", _clean({"collection": collection, "filter": filter}))["count"])

    def update(
        self,
        collection: str,
        target: Union[str, Dict[str, Any]],
        patch: Dict[str, Any],
        many: bool = False,
    ) -> Dict[str, Any]:
        """Update by ``_id`` (str target) or by filter (dict target).

        Pass ``many=True`` for every match — otherwise a multi-match returns
        HTTP 409 ``ambiguous_match``. Returns ``{updated, ids}``.
        """
        payload = {"id": target} if isinstance(target, str) else {"filter": target}
        return self._op("update", {"collection": collection, **payload, "patch": patch, "many": many})

    def replace(self, collection: str, id: str, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Replace a document by ``_id`` (keeps ``_id``/``_createdAt``). Returns ``{replaced}``."""
        return self._op("replace", {"collection": collection, "id": id, "doc": doc})

    def delete(
        self,
        collection: str,
        target: Union[str, Dict[str, Any]],
        many: bool = False,
    ) -> Dict[str, Any]:
        """Delete by ``_id`` or filter. Pass ``many=True`` for every match."""
        payload = {"id": target} if isinstance(target, str) else {"filter": target}
        return self._op("delete", {"collection": collection, **payload, "many": many})

    def list(self) -> List[Dict[str, Any]]:
        """List collections: ``[{name, count, bytes}]``."""
        return self._op("collections", {})["collections"]

    def drop(self, collection: str) -> Dict[str, Any]:
        """Drop a whole collection (needs schema permission). Returns ``{dropped, documents}``."""
        return self._op("drop", {"collection": collection})
