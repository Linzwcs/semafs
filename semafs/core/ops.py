"""
Operation commands (Ops) and RebalancePlan for knowledge tree reorganization.

This module defines the command objects that represent reorganization operations.
These are pure data carriers (frozen dataclasses) with no execution logic.

Design Principles:
    1. Ops are immutable data containers - they describe WHAT to do, not HOW
    2. LLM output is parsed into a RebalancePlan, which the Executor processes
    3. Each Op contains the semantic information decided by the LLM
    4. The Executor is responsible for applying operations to the tree

Operation Types:
    - MergeOp: Combine multiple semantically similar leaves into one
    - GroupOp: Create a new category and move leaves into it
    - MoveOp: Relocate a single leaf to an existing category
    - PersistOp: Convert a pending fragment to an active leaf (rule-based)

Usage:
    plan = RebalancePlan(
        ops=(MergeOp(ids=("id1", "id2"), content="merged", name="combined"),),
        updated_content="Category summary after merge",
    )
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple, Union

from .enums import OpType


@dataclass(frozen=True)
class MergeOp:
    """
    Merge operation: Combine multiple leaves into a single new leaf.

    When LLM determines that several leaves describe different facets of
    the same topic, it creates a MergeOp to consolidate them. The original
    leaves are archived, and a new leaf with synthesized content is created.

    Important: The merged content should be a superset of all original details.
    Specific values, dates, and proper nouns must NOT be lost in the merge.

    Attributes:
        ids: Tuple of at least 2 leaf node IDs to merge.
        content: LLM-generated synthesized content (not simple concatenation).
        name: System name for the new leaf (lowercase, underscores, a-z0-9_).
        reasoning: LLM's explanation for why this merge makes sense.
        op_type: Always OpType.MERGE (auto-set, not passed to __init__).

    Raises:
        ValueError: If fewer than 2 IDs are provided.

    Example:
        >>> MergeOp(
        ...     ids=("abc123", "def456"),
        ...     content="User prefers black coffee, specifically Americano without sugar",
        ...     name="coffee_preferences",
        ...     reasoning="Both fragments describe coffee drinking habits"
        ... )
    """
    ids: Tuple[str, ...]
    content: str
    name: str
    reasoning: str = ""
    op_type: OpType = field(default=OpType.MERGE, init=False)

    def __post_init__(self) -> None:
        if len(self.ids) < 2:
            raise ValueError(
                f"MergeOp requires at least 2 node IDs, got {len(self.ids)}"
            )


@dataclass(frozen=True)
class GroupOp:
    """
    Group operation: Create a new category and move leaves into it.

    When LLM identifies leaves that belong to the same broad topic but are
    distinct entities, it creates a GroupOp to organize them under a new
    subcategory. Original leaves are archived and recreated under the new category.

    Attributes:
        ids: Tuple of at least 2 leaf node IDs to group together.
        name: System name for the new category (lowercase, underscores).
        content: Summary/description for the new category (LLM-generated).
        reasoning: LLM's explanation for this grouping decision.
        op_type: Always OpType.GROUP (auto-set).

    Raises:
        ValueError: If fewer than 2 IDs or empty name provided.

    Example:
        >>> GroupOp(
        ...     ids=("id1", "id2", "id3"),
        ...     name="backend_specs",
        ...     content="Technical specifications for backend development",
        ...     reasoning="All three fragments relate to backend architecture"
        ... )
    """
    ids: Tuple[str, ...]
    name: str
    content: str = ""
    reasoning: str = ""
    op_type: OpType = field(default=OpType.GROUP, init=False)

    def __post_init__(self) -> None:
        if len(self.ids) < 2:
            raise ValueError(
                f"GroupOp requires at least 2 node IDs, got {len(self.ids)}"
            )
        if not self.name:
            raise ValueError("GroupOp must have a name for the new category")


@dataclass(frozen=True)
class MoveOp:
    """
    Move operation: Relocate a single leaf to an existing category.

    When a leaf clearly belongs in an existing subcategory, LLM creates a
    MoveOp. The target path must exist and be a CATEGORY - the operation
    will be skipped if the target doesn't exist (to prevent path fabrication).

    Attributes:
        ids: Tuple containing exactly 1 leaf node ID.
        path_to_move: Complete path to the target category (must exist).
        name: New name for the leaf after moving.
        reasoning: LLM's explanation for this move decision.
        op_type: Always OpType.MOVE (auto-set).

    Raises:
        ValueError: If not exactly 1 ID or empty path_to_move.

    Example:
        >>> MoveOp(
        ...     ids=("abc123",),
        ...     path_to_move="root.work.projects",
        ...     name="frontend_refactor",
        ...     reasoning="This fragment belongs in the projects category"
        ... )
    """
    ids: Tuple[str, ...]
    path_to_move: str
    name: str
    reasoning: str = ""
    op_type: OpType = field(default=OpType.MOVE, init=False)

    def __post_init__(self) -> None:
        if len(self.ids) != 1:
            raise ValueError(
                f"MoveOp must move exactly 1 node, got {len(self.ids)}"
            )
        if not self.path_to_move:
            raise ValueError("MoveOp must specify path_to_move")


@dataclass(frozen=True)
class PersistOp:
    """
    Persist operation: Convert a pending fragment to an active leaf.

    This operation is used by the rule-based strategy (no LLM) to simply
    promote PENDING_REVIEW fragments to ACTIVE leaves without semantic
    reorganization. It preserves the original content and metadata.

    Attributes:
        ids: Tuple containing exactly 1 fragment node ID.
        name: Name for the persisted leaf.
        content: Content for the leaf (usually same as fragment).
        payload: Metadata dict to attach to the leaf.
        reasoning: Always "Rule strategy: archive inbox fragment".
        op_type: Always OpType.PERSIST (auto-set).

    Raises:
        ValueError: If not exactly 1 ID provided.

    Example:
        >>> PersistOp(
        ...     ids=("frag_abc",),
        ...     name="leaf_abc12345",
        ...     content="User mentioned they like hiking",
        ...     payload={"_created_at": "2024-01-01T00:00:00"}
        ... )
    """
    ids: Tuple[str, ...]
    name: str
    content: str
    payload: dict
    reasoning: str = "Rule strategy: archive inbox fragment"
    op_type: OpType = field(default=OpType.PERSIST, init=False)

    def __post_init__(self) -> None:
        if len(self.ids) != 1:
            raise ValueError("PersistOp handles exactly 1 node at a time")


# Union type for any operation
AnyOp = Union[MergeOp, GroupOp, MoveOp, PersistOp]


@dataclass(frozen=True)
class RebalancePlan:
    """
    A reorganization plan produced by Strategy for Executor to apply.

    RebalancePlan is the output of LLM's deliberation on how to reorganize
    a category's contents. It contains an ordered list of operations and
    metadata about the category's new state after execution.

    An empty ops list is valid - it means LLM determined the current
    structure is healthy, but updated_content may still need refreshing.

    Attributes:
        ops: Ordered tuple of operations to execute sequentially.
        updated_content: New summary for the category after all ops complete.
        updated_name: New display name for category (optional, LLM decides).
        overall_reasoning: LLM's explanation of the reorganization strategy.
        should_dirty_parent: Whether to mark parent as dirty for cascade update.
        is_llm_plan: True if generated by LLM, False if rule-based fallback.

    Properties:
        is_empty: True if no structural changes (ops list empty).
        ops_summary: Human-readable summary of operations for logging.

    Example:
        >>> plan = RebalancePlan(
        ...     ops=(merge_op, group_op),
        ...     updated_content="Category now contains organized knowledge",
        ...     overall_reasoning="Consolidated duplicates and grouped related items",
        ...     should_dirty_parent=True
        ... )
    """
    ops: Tuple[AnyOp, ...]
    updated_content: str
    updated_name: Optional[str] = None
    overall_reasoning: str = ""
    should_dirty_parent: bool = False
    is_llm_plan: bool = True

    @property
    def is_empty(self) -> bool:
        """Check if plan has no structural changes (summary-only update)."""
        return len(self.ops) == 0

    @property
    def ops_summary(self) -> str:
        """
        Generate a human-readable summary of operations.

        Returns:
            String like "MERGE×2 | GROUP×1" or "(summary update only)".
        """
        if self.is_empty:
            return "(summary update only)"
        counts: dict[str, int] = {}
        for op in self.ops:
            k = op.op_type.value
            counts[k] = counts.get(k, 0) + 1
        return " | ".join(f"{k}×{v}" for k, v in counts.items())


@dataclass(frozen=True)
class UpdateContext:
    """
    Read-only snapshot of category state for Strategy and Executor.

    UpdateContext captures all information needed to make reorganization
    decisions at a specific point in time. It's created at the start of
    maintenance and used throughout the process, ensuring consistency
    even if the database changes during execution.

    The context includes:
    - The parent category being maintained
    - Its active and pending children
    - Sibling categories (to avoid naming conflicts)
    - Ancestor chain (to provide hierarchical semantic context)

    Attributes:
        parent: The CATEGORY node being maintained.
        active_nodes: Tuple of ACTIVE children (stable, organized nodes).
        pending_nodes: Tuple of PENDING_REVIEW children (new fragments).
        sibling_categories: Tuple of parent's sibling CATEGORYs (for naming).
        ancestor_categories: Tuple of ancestors from parent to root (near→far).

    Properties:
        inbox: Alias for pending_nodes (semantic clarity).
        children: Alias for active_nodes (semantic clarity).
        all_nodes: Combined tuple of active and pending nodes.
        sibling_category_names: Quick access to sibling names as strings.
        ancestor_path_chain: Full path chain from root to parent.
    """
    from .node import TreeNode  # Deferred import to avoid circular dependency

    parent: "TreeNode"
    active_nodes: Tuple["TreeNode", ...]  # Organized, stable nodes
    pending_nodes: Tuple["TreeNode", ...]  # New fragments (PENDING_REVIEW)
    sibling_categories: Tuple["TreeNode", ...] = ()  # Parent's siblings
    ancestor_categories: Tuple["TreeNode", ...] = ()  # Ancestor chain (near→far)

    @property
    def inbox(self) -> Tuple["TreeNode", ...]:
        """Semantic alias for pending_nodes (fragments awaiting organization)."""
        return self.pending_nodes

    @property
    def children(self) -> Tuple["TreeNode", ...]:
        """Semantic alias for active_nodes (organized children)."""
        return self.active_nodes

    @property
    def all_nodes(self) -> Tuple["TreeNode", ...]:
        """Combined tuple of all nodes (active + pending)."""
        return self.active_nodes + self.pending_nodes

    @property
    def sibling_category_names(self) -> Tuple[str, ...]:
        """Tuple of sibling category names for quick conflict checking."""
        return tuple(s.name for s in self.sibling_categories)

    @property
    def ancestor_path_chain(self) -> Tuple[str, ...]:
        """Full path chain from root to parent (far→near order)."""
        return tuple(reversed([a.path for a in self.ancestor_categories
                               ])) + (self.parent.path, )
