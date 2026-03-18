"""Shared naming rules and unique allocation helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha1

_INVALID_CHARS_RE = re.compile(r"[^a-z0-9_]+")
_DUP_UNDERSCORE_RE = re.compile(r"_+")


def normalize_name(raw_name: str, *, fallback_prefix: str = "node") -> str:
    """
    Normalize arbitrary input into a valid SemaFS node name.

    Output format is always `[a-z0-9_]+`.
    """
    base = (raw_name or "").strip().lower()
    base = base.replace("-", "_").replace(" ", "_")
    base = _INVALID_CHARS_RE.sub("_", base)
    base = _DUP_UNDERSCORE_RE.sub("_", base).strip("_")
    if not base:
        digest = sha1((raw_name or "").encode("utf-8")).hexdigest()[:6]
        return f"{fallback_prefix}_{digest}"
    return base


def allocate_unique_name(
    *,
    raw_name: str,
    used_names: set[str],
    fallback_prefix: str = "node",
) -> str:
    """
    Normalize then allocate a unique name by suffixing `_N` when needed.

    This helper mutates `used_names` by inserting the selected name.
    """
    base = normalize_name(raw_name, fallback_prefix=fallback_prefix)
    if base not in used_names:
        used_names.add(base)
        return base

    counter = 1
    while True:
        candidate = f"{base}_{counter}"
        if candidate not in used_names:
            used_names.add(candidate)
            return candidate
        counter += 1


@dataclass(frozen=True)
class PathAllocator:
    """Single point for name/path allocation policy."""

    default_fallback_prefix: str = "node"

    def normalize(self,
                  raw_name: str,
                  *,
                  fallback_prefix: str | None = None) -> str:
        prefix = fallback_prefix or self.default_fallback_prefix
        return normalize_name(raw_name, fallback_prefix=prefix)

    def allocate_name(
        self,
        *,
        raw_name: str,
        used_names: set[str],
        fallback_prefix: str | None = None,
    ) -> str:
        prefix = fallback_prefix or self.default_fallback_prefix
        return allocate_unique_name(
            raw_name=raw_name,
            used_names=used_names,
            fallback_prefix=prefix,
        )

    def allocate_path(
        self,
        *,
        parent_path: str,
        raw_name: str,
        used_paths: set[str],
        fallback_prefix: str | None = None,
    ) -> str:
        sibling_names = self.sibling_names(parent_path=parent_path,
                                           used_paths=used_paths)
        name = self.allocate_name(
            raw_name=raw_name,
            used_names=sibling_names,
            fallback_prefix=fallback_prefix,
        )
        if parent_path == "root":
            path = f"root.{name}"
        else:
            path = f"{parent_path}.{name}"
        used_paths.add(path)
        return path

    @staticmethod
    def sibling_names(*, parent_path: str, used_paths: set[str]) -> set[str]:

        def _parent_of(path: str) -> str | None:
            if path == "root" or "." not in path:
                return None
            return path.rsplit(".", 1)[0]

        return {
            path.rsplit(".", 1)[-1]
            for path in used_paths if _parent_of(path) == parent_path
        }
