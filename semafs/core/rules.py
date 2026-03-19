"""Shared semantic/naming rules used across planner pipeline."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .node import Node

CATEGORY_UPDATED_NAME_RE = re.compile(r"^[a-z]+$")
CATEGORY_SEGMENT_RE = re.compile(r"^[a-z]+$")
_NON_ALPHA_RE = re.compile(r"[^a-z]+")
_TOKEN_RE = re.compile(r"[a-z]{3,}")
_GENERIC_PATTERN = re.compile(
    r"^(group|batch|misc|temp|tmp|other|others|general|"
    r"newrecords|records?)([a-z0-9]*)$"
)

GENERIC_CATEGORY_NAMES: frozenset[str] = frozenset(
    {
        "new_records",
        "records",
        "misc",
        "others",
        "other",
        "temp",
        "tmp",
        "untitled",
        "general",
    }
)


def is_generic_category_name(name: str | None) -> bool:
    """Return True if name is a blocked placeholder category name."""
    if not name:
        return False
    normalized = name.strip().lower().replace("_", "")
    if normalized in GENERIC_CATEGORY_NAMES:
        return True
    return _GENERIC_PATTERN.fullmatch(normalized) is not None


def normalize_category_segment(
    raw_name: str,
    *,
    fallback: str = "topic",
) -> str:
    """Normalize category segment to a single english word."""
    cleaned = _NON_ALPHA_RE.sub("", (raw_name or "").strip().lower())
    return cleaned or fallback


def semantic_category_segment(
    raw_name: str,
    *,
    context_text: str = "",
    fallback: str = "topic",
) -> str:
    """
    Produce a semantic category segment.

    If raw segment is placeholder-like (groupa/batchx/etc), try to recover
    from context text; otherwise keep normalized raw segment.
    """
    base = normalize_category_segment(raw_name, fallback=fallback)
    if not is_generic_category_name(base):
        return base
    for token in _TOKEN_RE.findall((context_text or "").lower()):
        if is_generic_category_name(token):
            continue
        return token
    return fallback


def _alpha_suffix(index: int) -> str:
    """Convert 1-based index to alphabetic suffix: 1->a, 27->aa."""
    chars: list[str] = []
    current = index
    while current > 0:
        current -= 1
        chars.append(chr(ord("a") + (current % 26)))
        current //= 26
    return "".join(reversed(chars))


def allocate_unique_category_segment(
    raw_name: str,
    *,
    used_names: set[str],
    fallback: str = "topic",
) -> str:
    """
    Allocate unique category segment while keeping `^[a-z]+$`.

    Uniqueness suffix is alphabetic only: `topic`, `topica`, `topicb`, ...
    """
    base = normalize_category_segment(raw_name, fallback=fallback)
    if base not in used_names:
        used_names.add(base)
        return base

    index = 1
    while True:
        candidate = f"{base}{_alpha_suffix(index)}"
        if candidate not in used_names:
            used_names.add(candidate)
            return candidate
        index += 1


def is_name_locked_node(node: "Node") -> bool:
    """
    Whether category node name is locked by policy.

    Moved from guard.py to core/rules.py to:
    1. Eliminate infra -> engine reverse dependency
    2. Make rule available to all layers
    """
    from .node import NodeType  # Local import to avoid circular dependency

    if node.node_type != NodeType.CATEGORY:
        return False
    return not node.name_editable
