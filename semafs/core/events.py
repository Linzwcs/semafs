"""Domain events - Immutable records of what happened."""

from dataclasses import dataclass
from typing import Optional, Union

# Union type for all domain events
TreeEvent = Union[
    "Merged", "Grouped", "Moved", "Persisted", "Placed", "RolledUp", "Archived"
]


@dataclass(frozen=True)
class Merged:
    """Event: Multiple leaves were merged into one."""

    source_ids: tuple[str, ...]  # IDs of merged leaves
    result_id: str  # ID of resulting leaf
    parent_id: str  # Parent category ID
    result_path: str  # Path of resulting leaf
    parent_path: str  # Parent category path


@dataclass(frozen=True)
class Grouped:
    """Event: Leaves were grouped into a new category."""

    source_ids: tuple[str, ...]  # IDs of grouped leaves
    category_id: str  # ID of new category
    parent_id: str  # Parent category ID
    category_path: str  # Path of new category
    parent_path: str  # Parent category path


@dataclass(frozen=True)
class Moved:
    """Event: A leaf was moved to another category."""

    leaf_id: str  # ID of moved leaf
    target_category_id: str  # Target category ID
    old_path: str  # Old path
    new_path: str  # New path
    target_category: str  # Target category path


@dataclass(frozen=True)
class Persisted:
    """Event: A pending fragment was persisted as active leaf."""

    leaf_id: str  # ID of persisted leaf
    parent_id: str  # Parent category ID
    leaf_path: str  # Path of leaf
    parent_path: str  # Parent category path


@dataclass(frozen=True)
class Placed:
    """Event: A new fragment was placed in a category."""

    leaf_id: str  # ID of placed leaf
    parent_id: str  # Parent category ID
    leaf_path: str  # Path of leaf
    parent_path: str  # Parent category path
    routed: bool  # Whether it was routed (True) or direct write (False)
    reasoning: Optional[str] = None  # Routing reasoning if applicable


@dataclass(frozen=True)
class RolledUp:
    """Event: Multiple leaves were rolled up into a summary."""

    source_ids: tuple[str, ...]  # IDs of rolled up leaves
    rollup_id: str  # ID of rollup summary node
    parent_id: str  # Parent category ID
    rollup_path: str  # Path of rollup node
    parent_path: str  # Parent category path
    window_label: str  # e.g., "2026-w12"


@dataclass(frozen=True)
class Archived:
    """Event: Nodes were archived."""

    source_ids: tuple[str, ...]  # IDs of archived nodes
    parent_id: str  # Parent category ID
    parent_path: str  # Parent category path
    reason: str  # Reason for archiving
