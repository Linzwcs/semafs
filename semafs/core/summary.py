"""Category metadata helpers (v2.1.8 minimal contract)."""

from __future__ import annotations

import re
from typing import Any

_LEAF_LIKE_RE = re.compile(r"^(leaf|rollup)_[0-9a-z_]+$")
_TIME_LIKE_RE = re.compile(r"^\\d{1,2}:\\d{2}$")
_MAX_SUMMARY_CHARS = 1200
_MAX_KEYWORDS = 6
_STOPWORDS = {
    "and", "or", "the", "a", "an", "of", "to", "in", "on", "for",
    "with", "from", "by", "is", "are", "be", "this", "that",
}


def build_category_meta(
    *,
    raw_summary: str | None,
    leaf_texts: tuple[str, ...] = (),
    child_names: tuple[str, ...] = (),
    keywords: tuple[str, ...] | None = None,
    ext: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build minimal category meta contract:
    {keywords: list[str], summary: str, ext: dict}
    """
    summary = _normalize_summary(raw_summary)
    if not summary:
        summary = _fallback_summary(leaf_texts)

    if keywords:
        normalized_keywords = _normalize_keywords(keywords)
        keyword_source = "llm"
    else:
        normalized_keywords = ()
        keyword_source = "none"

    ext_payload = dict(ext or {})
    ext_payload["keyword_source"] = keyword_source

    return {
        "keywords": list(normalized_keywords),
        "summary": summary,
        "ext": ext_payload,
    }


def normalize_category_meta(meta: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize arbitrary input into minimal category meta contract."""
    source = meta or {}
    raw_keywords = source.get("keywords", [])
    if isinstance(raw_keywords, (list, tuple)):
        normalized_keywords = _normalize_keywords(
            tuple(str(v) for v in raw_keywords)
        )
    else:
        normalized_keywords = ()
    summary = _normalize_summary(str(source.get("summary", "")))
    ext = source.get("ext", {})
    if not isinstance(ext, dict):
        ext = {}
    ext.setdefault("keyword_source", "none")
    return {
        "keywords": list(normalized_keywords),
        "summary": summary or "No summary available.",
        "ext": dict(ext),
    }


def render_category_summary(category_meta: dict[str, Any]) -> str:
    """Render human-readable summary from meta."""
    normalized = normalize_category_meta(category_meta)
    return normalized["summary"][:_MAX_SUMMARY_CHARS]


def _normalize_summary(value: str | None) -> str:
    if not value:
        return ""
    text = value.replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:800]


def _fallback_summary(leaf_texts: tuple[str, ...]) -> str:
    snippets = []
    for text in leaf_texts:
        cleaned = _normalize_summary(text)
        if cleaned:
            snippets.append(cleaned[:80])
        if len(snippets) >= 3:
            break
    return "; ".join(snippets) if snippets else "No summary available."


def _normalize_keywords(values: tuple[str, ...]) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        token = _normalize_summary(value).lower()
        if not _is_semantic_keyword(token):
            continue
        if token in seen:
            continue
        seen.add(token)
        out.append(token)
        if len(out) >= _MAX_KEYWORDS:
            break
    return tuple(out)


def _is_semantic_keyword(token: str) -> bool:
    if not token:
        return False
    if token in _STOPWORDS:
        return False
    if _TIME_LIKE_RE.fullmatch(token):
        return False
    if _LEAF_LIKE_RE.fullmatch(token):
        return False
    if any(ch in token for ch in (":", "/", "\\")):
        return False
    return True
