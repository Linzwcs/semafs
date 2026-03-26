"""Operations and Plans - Executable reorganization instructions."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class MergeOp:
    """Merge multiple leaves into one."""

    source_ids: tuple[str, ...]  # IDs to merge
    new_content: str  # Merged content
    new_name: str  # Name for merged leaf


@dataclass(frozen=True)
class GroupOp:
    """Group leaves into a new category."""

    source_ids: tuple[str, ...]  # IDs to group
    category_path: str  # Absolute target category path
    category_summary: str  # Category summary
    category_keywords: tuple[str, ...]  # Category keywords


@dataclass(frozen=True)
class MoveOp:
    """Move a leaf to an existing category."""

    leaf_id: str  # ID of moved leaf
    target_path: str  # Target category path (resolved)


@dataclass(frozen=True)
class RenameOp:
    """Rename a node under the same parent."""

    node_id: str
    new_name: str


@dataclass(frozen=True)
class RollupOp:
    """Roll up multiple leaves into a summary node."""

    source_ids: tuple[str, ...]
    rollup_summary: str
    rollup_keywords: tuple[str, ...]
    highlights: tuple[str, ...]
    window_label: str  # e.g., "2026-w12"


@dataclass(frozen=True)
class ArchiveOp:
    """Archive nodes (move to ARCHIVED stage)."""

    source_ids: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class Plan:
    """
    Executable reorganization plan.

    Contains resolved operations ready for execution.
    All paths are fully resolved (no relative references).
    """

    ops: tuple[MergeOp | GroupOp | MoveOp | RenameOp | RollupOp | ArchiveOp,
               ...]
    updated_summary: Optional[str] = None  # Updated parent summary
    updated_keywords: tuple[str, ...] = ()  # Updated parent keywords
    updated_name: Optional[str] = None  # Updated parent name
    reasoning: Optional[str] = None  # Overall reasoning

    def is_empty(self) -> bool:
        """Check if plan has no operations."""
        return len(self.ops) == 0

    def has_summary_update(self) -> bool:
        """Check if plan updates parent summary."""
        return self.updated_summary is not None

    def has_keywords_update(self) -> bool:
        """Check if plan updates parent keywords."""
        return len(self.updated_keywords) > 0

    def has_name_update(self) -> bool:
        """Check if plan updates parent name."""
        return self.updated_name is not None

