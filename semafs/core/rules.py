from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .node import Node

CATEGORY_UPDATED_NAME_RE = re.compile(r"^[a-z]+$")
CATEGORY_SEGMENT_RE = re.compile(r"^[a-z]+$")
_NON_ALPHA_RE = re.compile(r"[^a-z]+")
_TOKEN_RE = re.compile(r"[a-z]{3,}")
_SEMANTIC_TOKEN_RE = re.compile(r"[a-z]{3,}")

_GENERIC_PATTERN = re.compile(
    r"^(group|batch|misc|temp|tmp|other|others|general|"
    r"newrecords|records?)([a-z0-9]*)$")

_SEMANTIC_STOPWORDS = frozenset({
    "and",
    "or",
    "the",
    "a",
    "an",
    "of",
    "to",
    "in",
    "on",
    "for",
    "with",
    "from",
    "by",
    "is",
    "are",
    "be",
    "this",
    "that",
    "under",
    "into",
    "within",
    "across",
    "category",
    "categories",
    "group",
    "groups",
    "cluster",
    "clusters",
    "related",
    "semantic",
    "subtree",
    "notes",
    "items",
    "item",
})
_WEAK_PREFIX_TOKENS = frozenset({
    "best",
    "core",
    "main",
    "general",
    "misc",
    "other",
    "topic",
    "topics",
})
_SEMANTIC_FAMILIES = (frozenset({
    "work",
    "workflow",
    "practice",
    "practices",
    "process",
    "processes",
    "task",
    "tasks",
    "operation",
    "operations",
    "procedure",
    "procedures",
}), )

GENERIC_CATEGORY_NAMES: frozenset[str] = frozenset({
    "new_records",
    "records",
    "misc",
    "others",
    "other",
    "temp",
    "tmp",
    "untitled",
    "general",
})


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

    Centralized in core/rules.py to:
    1. Eliminate infra -> engine reverse dependency
    2. Make rule available to all layers
    """
    from .node import NodeType  # Local import to avoid circular dependency

    if node.node_type != NodeType.CATEGORY:
        return False
    return not node.name_editable


def canonical_semantic_token(token: str) -> str:
    """Normalize token for semantic overlap checks."""
    text = re.sub(r"[^a-z]", "", (token or "").strip().lower())
    if not text:
        return ""

    if text.endswith("ies") and len(text) > 4:
        text = text[:-3] + "y"
    elif text.endswith(("ches", "shes", "sses", "xes", "zes")):
        text = text[:-2]
    elif text.endswith("s") and not text.endswith("ss") and len(text) > 3:
        text = text[:-1]
    return text


def extract_semantic_tokens(*texts: str) -> frozenset[str]:
    """Extract normalized semantic tokens from free text."""
    out: set[str] = set()
    for text in texts:
        lowered = (text or "").lower()
        for raw in _SEMANTIC_TOKEN_RE.findall(lowered):
            token = canonical_semantic_token(raw)
            if not token or token in _SEMANTIC_STOPWORDS:
                continue
            out.add(token)
    return frozenset(out)


def semantic_overlap_ratio(
    left_tokens: set[str] | frozenset[str],
    right_tokens: set[str] | frozenset[str],
) -> float:
    """Compute overlap ratio over smaller token set."""
    left = set(left_tokens)
    right = set(right_tokens)
    if not left or not right:
        return 0.0
    shared = left & right
    if not shared:
        return 0.0
    base = min(len(left), len(right))
    if base <= 0:
        return 0.0
    return len(shared) / float(base)


def is_lexical_variant_name(left: str, right: str) -> bool:
    """Return True when two category names are lexical near-duplicates."""
    a = re.sub(r"[^a-z]", "", (left or "").strip().lower())
    b = re.sub(r"[^a-z]", "", (right or "").strip().lower())
    if not a or not b:
        return False
    if a == b:
        return True

    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if len(shorter) >= 4 and len(longer) - len(shorter) <= 2:
        if longer.startswith(shorter) or longer.endswith(shorter):
            return True
    if (len(shorter) >= 6
            and (longer.startswith(shorter) or longer.endswith(shorter))):
        return True
    if (shorter in _WEAK_PREFIX_TOKENS and len(shorter) >= 4
            and len(longer) - len(shorter) >= 5
            and (longer.startswith(shorter) or longer.endswith(shorter))):
        return True

    if canonical_semantic_token(a) == canonical_semantic_token(b):
        return True
    return same_semantic_family(a, b)


def same_semantic_family(left: str, right: str) -> bool:
    """Return True when two names belong to same coarse semantic family."""
    a = canonical_semantic_token(left)
    b = canonical_semantic_token(right)
    if not a or not b:
        return False
    if a == b:
        return True
    for family in _SEMANTIC_FAMILIES:
        if a in family and b in family:
            return True
    return False
