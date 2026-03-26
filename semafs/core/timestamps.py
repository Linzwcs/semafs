"""Timestamp helpers for consistent memory read/write metadata."""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now_rfc3339() -> str:
    """Return current UTC timestamp in RFC3339 format."""
    return datetime.now(timezone.utc).isoformat()


def normalize_rfc3339(value: str | None) -> str | None:
    """
    Normalize common timestamp strings to RFC3339 UTC offset form.

    Accepts:
    - `2026-03-24T10:12:00Z`
    - `2026-03-24T10:12:00+00:00`
    - naive datetime string (interpreted as UTC)
    """
    if not value or not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()

