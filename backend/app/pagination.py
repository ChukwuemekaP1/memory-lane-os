"""Cursor pagination helpers (API_SPECIFICATION Section 3)."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from app.errors import AppError

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


@dataclass(frozen=True)
class Cursor:
    # created_at carries the sort-key value (created_at, or effective
    # taken_at for taken_* sorts); callers must reuse the same sort.
    created_at: datetime
    id: UUID

    def encode(self) -> str:
        raw = json.dumps({"t": self.created_at.isoformat(), "i": str(self.id)})
        return base64.urlsafe_b64encode(raw.encode()).decode()

    @staticmethod
    def decode(value: str) -> Cursor:
        try:
            raw = json.loads(base64.urlsafe_b64decode(value.encode()).decode())
            return Cursor(created_at=datetime.fromisoformat(raw["t"]), id=UUID(raw["i"]))
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
            raise AppError("validation_error", "Invalid pagination cursor.", 422) from e


def normalize_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    if limit < 1 or limit > MAX_LIMIT:
        raise AppError("validation_error", f"limit must be between 1 and {MAX_LIMIT}.", 422)
    return limit


def page_payload(items: list[Any], next_cursor: str | None) -> dict[str, Any]:
    from app.logging import request_id_ctx
    return {
        "data": items,
        "page": {"next_cursor": next_cursor, "has_more": next_cursor is not None},
        "request_id": request_id_ctx.get(),
    }
