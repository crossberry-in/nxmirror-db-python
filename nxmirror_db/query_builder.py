"""Fluent query builder for the NxMirror DB SQL engine (JS SDK parity)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Union

from .errors import NxError

if TYPE_CHECKING:  # pragma: no cover — typing only, avoids a circular import
    from .client import NxDatabase

_OPS = {"eq": "=", "ne": "!=", "gt": ">", "lt": "<", "gte": ">=", "lte": "<=", "like": "LIKE"}

_EMPTY_RESULT = {
    "rows": [],
    "columns": [],
    "changes": 0,
    "executionMs": 0,
    "lastInsertRowid": None,
    "truncated": False,
}


class NxQueryBuilder:
    """``db.table("users").where(...).orderBy(...).limit(...).select()``"""

    def __init__(self, client: "NxDatabase", table: str):
        self.client = client
        self.table = table
        self._where: List[str] = []
        self._params: List[Any] = []
        self._order_by: Optional[str] = None
        self._limit: Optional[int] = None
        self._offset: Optional[int] = None
        self._columns: Optional[List[str]] = None

    def select(self, columns: Optional[Sequence[str]] = None) -> Dict[str, Any]:
        self._columns = list(columns) if isinstance(columns, (list, tuple)) else None
        return self._run()

    def count(self) -> int:
        result = self.client.query(f'SELECT COUNT(*) AS __n FROM "{self.table}"{self._where_sql()}', self._params)
        rows = result["rows"]
        return int(rows[0]["__n"]) if rows and rows[0].get("__n") is not None else 0

    def where(self, *args: Any) -> "NxQueryBuilder":
        """``where("age", ">", 18)`` or ``where({"active": True})`` (AND-combined)."""
        if len(args) == 1 and isinstance(args[0], dict):
            for key, value in args[0].items():
                if value is None:
                    self.where_null(key)
                else:
                    self._where.append(f'"{key}" = ?')
                    self._params.append(value)
            return self
        key, op, value = args
        if op == "in":
            if not isinstance(value, (list, tuple)) or not len(value):
                self._where.append("0 = 1")
                return self
            self._where.append(f'"{key}" IN ({", ".join(["?"] * len(value))})')
            self._params.extend(value)
            return self
        if op == "isNull":
            self._where.append(f'"{key}" IS NULL')
            return self
        sql_op = _OPS.get(op, op)
        self._where.append(f'"{key}" {sql_op} ?')
        self._params.append(value)
        return self

    def where_null(self, key: str) -> "NxQueryBuilder":
        self._where.append(f'"{key}" IS NULL')
        return self

    # camelCase alias
    whereNull = where_null

    def order_by(self, column: str, direction: str = "ASC") -> "NxQueryBuilder":
        self._order_by = f'"{column}" {"DESC" if str(direction).upper() == "DESC" else "ASC"}'
        return self

    orderBy = order_by

    def limit(self, n: int) -> "NxQueryBuilder":
        self._limit = max(0, min(1000, int(n or 0)))
        return self

    def offset(self, n: int) -> "NxQueryBuilder":
        self._offset = max(0, int(n or 0))
        return self

    def insert(self, data: Union[Dict[str, Any], List[Dict[str, Any]]]) -> Dict[str, Any]:
        rows = data if isinstance(data, list) else [data]
        if not rows:
            return dict(_EMPTY_RESULT)
        keys = list(rows[0].keys())
        sql = (
            f'INSERT INTO "{self.table}" '
            f'({", ".join(chr(34) + k + chr(34) for k in keys)}) '
            f'VALUES ({", ".join(["?"] * len(keys))})'
        )
        result = dict(_EMPTY_RESULT)
        for row in rows:
            r = self.client.query(sql, [row.get(k) for k in keys])
            result["changes"] += r["changes"]
            result["executionMs"] += r["executionMs"]
            if r["lastInsertRowid"] is not None:
                result["lastInsertRowid"] = r["lastInsertRowid"]
        return result

    def update(self, patch: Dict[str, Any], where: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if where:
            self.where(where)
        sets = [f'"{k}" = ?' for k in patch.keys()]
        params = list(patch.values()) + self._params
        if not sets:
            raise NxError("update() needs at least one column to set.", "invalid_input")
        return self.client.query(f'UPDATE "{self.table}" SET {", ".join(sets)}{self._where_sql()}', params)

    def delete(self, where: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if where:
            self.where(where)
        if not self._where:
            raise NxError(
                "delete() refuses to run without a WHERE clause — pass where() or delete({'id': ...}).",
                "invalid_input",
            )
        return self.client.query(f'DELETE FROM "{self.table}"{self._where_sql()}', self._params)

    # ---------------- internals ----------------

    def _where_sql(self) -> str:
        return (" WHERE " + " AND ".join(self._where)) if self._where else ""

    def _run(self) -> Dict[str, Any]:
        cols = ", ".join(f'"{c}"' for c in self._columns) if self._columns else "*"
        sql = f'SELECT {cols} FROM "{self.table}"{self._where_sql()}'
        if self._order_by:
            sql += f" ORDER BY {self._order_by}"
        if self._limit is not None:
            sql += f" LIMIT {self._limit}"
        if self._offset is not None:
            sql += f" OFFSET {self._offset}"
        return self.client.query(sql, self._params)
