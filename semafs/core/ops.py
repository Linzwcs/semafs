"""Operations and Plans - Executable reorganization instructions."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class MergeOp:
    """Merge multiple leaves into one."""

    source_ids: tuple[str, ...]  # IDs to merge
    new_content: str             # Merged content
    new_name: str                # Name for merged leaf


@dataclass(frozen=True)
class GroupOp:
    """Group leaves into a new category."""

    source_ids: tuple[str, ...]  # IDs to group
    category_name: str           # New category name
    category_summary: str        # Category summary


@dataclass(frozen=True)
class MoveOp:
    """Move a leaf to an existing category."""

    leaf_id: str                 # ID to move
    target_path: str             # Target category path (resolved)


@dataclass(frozen=True)
class PersistOp:
    """Persist a pending fragment as active leaf (rule-only fallback)."""

    leaf_id: str                 # ID to persist


@dataclass(frozen=True)
class Plan:
    """
    Executable reorganization plan.

    Contains resolved operations ready for execution.
    All paths are fully resolved (no relative references).
    """

    ops: tuple[MergeOp | GroupOp | MoveOp | PersistOp, ...]
    updated_summary: Optional[str] = None  # Updated parent summary
    updated_name: Optional[str] = None     # Updated parent name
    reasoning: Optional[str] = None        # Overall reasoning

    def is_empty(self) -> bool:
        """Check if plan has no operations."""
        return len(self.ops) == 0

    def has_summary_update(self) -> bool:
        """Check if plan updates parent summary."""
        return self.updated_summary is not None

    def has_name_update(self) -> bool:
        """Check if plan updates parent name."""
        return self.updated_name is not None
