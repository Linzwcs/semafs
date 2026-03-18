"""Snapshot - Immutable context for maintenance operations."""

from dataclasses import dataclass

from .capacity import Budget
from .node import Node


@dataclass(frozen=True)
class Snapshot:
    """
    Immutable snapshot of a category's state for maintenance.

    Design principles:
    - Complete: Contains all information needed for decision-making
    - Immutable: Frozen dataclass, no mutations
    - Self-contained: No database queries during execution
    """

    target: Node                          # The category being maintained
    leaves: tuple[Node, ...]              # Active leaf children
    subcategories: tuple[Node, ...]       # Active subcategory children
    pending: tuple[Node, ...]             # Pending fragments (new writes)
    siblings: tuple[Node, ...]            # Sibling categories (for naming)
    ancestors: tuple[Node, ...]           # Ancestor chain (for context)
    budget: Budget                        # Capacity limits
    used_paths: frozenset[str]            # All paths in use (for uniqueness)
    cold_leaves: tuple[Node, ...] = ()    # Cold leaves (rolled up, retrievable)

    @property
    def total_children(self) -> int:
        """Total number of children (leaves + subcategories + pending)."""
        return len(self.leaves) + len(self.subcategories) + len(self.pending)

    @property
    def active_children(self) -> int:
        """Number of active children (leaves + subcategories)."""
        return len(self.leaves) + len(self.subcategories)

    @property
    def has_pending(self) -> bool:
        """Check if there are pending fragments."""
        return len(self.pending) > 0

    @property
    def zone(self):
        """Get capacity zone based on total children."""
        return self.budget.zone(self.total_children)

    @property
    def sibling_names(self) -> frozenset[str]:
        """Get set of sibling category names."""
        return frozenset(s.name for s in self.siblings)

    @property
    def ancestor_paths(self) -> tuple[str, ...]:
        """Get tuple of ancestor paths."""
        return tuple(a.path.value for a in self.ancestors)

    def is_path_available(self, path: str) -> bool:
        """Check if a path is available for use."""
        return path not in self.used_paths
