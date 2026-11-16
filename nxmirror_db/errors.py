"""SDK error type and shared limits shared by every module."""
from __future__ import annotations

from typing import Optional

SINGLE_UPLOAD_MAX = 3.4 * 1024 * 1024          # single-request upload ceiling (server limit 3.5 MB)
RESUMABLE_PART_SIZE = 3 * 1024 * 1024
RESUMABLE_MAX_TOTAL = 50 * 1024 * 1024


class NxError(Exception):
    """Every SDK failure raises NxError with a stable ``code`` and, for server
    errors, an HTTP ``status``. Catch by code — never by parsing messages."""

    def __init__(self, message: str, code: str = "error", status: Optional[int] = None):
        super().__init__(message)
        self.code = code
        self.status = status
