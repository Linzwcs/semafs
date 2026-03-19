"""Raw operations - LLM output before path resolution."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class RawMerge:
    """Raw merge operation from LLM (before resolution)."""

    source_ids: tuple[str, ...]  # Short IDs from LLM
    new_content: str
    new_name: str
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class RawGroup:
    """Raw group operation from LLM (before resolution)."""

    source_ids: tuple[str, ...]  # Short IDs from LLM
    category_name: str
    category_summary: str
    category_keywords: tuple[str, ...] = ()


@dataclass(frozen=True)
class RawMove:
    """Raw move operation from LLM (before resolution)."""

    leaf_id: str                 # Short ID from LLM
    target_name: str             # Relative name (needs resolution)


@dataclass(frozen=True)
class RawRename:
    """Raw rename operation from LLM (before resolution)."""

    node_id: str
    new_name: str


@dataclass(frozen=True)
class RawRollup:
    """Raw rollup operation from LLM (before resolution)."""

    source_ids: tuple[str, ...]  # Short IDs from LLM
    rollup_summary: str
    rollup_keywords: tuple[str, ...] = ()
    highlights: tuple[str, ...] = ()
    window_label: str = ""  # e.g., "2026-w12"


@dataclass(frozen=True)
class RawPlan:
    """
    Raw plan from LLM output (before resolution).

    Contains operations with short IDs and relative paths.
    Must be resolved to Plan before execution.
    """

    ops: tuple[RawMerge | RawGroup | RawMove | RawRename | RawRollup, ...]
    updated_summary: Optional[str] = None
    updated_keywords: tuple[str, ...] = ()
    updated_name: Optional[str] = None
    reasoning: Optional[str] = None
