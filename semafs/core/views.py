"""
View layer: Structured query views for the knowledge tree.

This module defines immutable view objects that provide structured access
to the knowledge tree for both LLM consumption and API responses.

Design Philosophy:
    1. Views are data containers, NOT TreeNodes - they're optimized for reading
    2. Each view has a specific semantic purpose (single node, tree, navigation)
    3. Views include navigation context (breadcrumbs, counts) for LLM orientation
    4. All views are frozen dataclasses - immutable after creation
    5. Rendering is delegated to Renderer classes (separation of concerns)

View Types:
    - NodeView: Single node with navigation context
    - TreeView: Recursive tree structure for exploration
    - RelatedNodes: Navigation map showing surrounding nodes
    - StatsView: Knowledge base statistics and metrics

Usage:
    # Get a single node with context
    view = await semafs.read("root.work")
    print(f"Path: {view.path}, Children: {view.child_count}")

    # Get tree structure
    tree = await semafs.view_tree("root", max_depth=3)
    print(f"Total nodes: {tree.total_nodes}")
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from .node import TreeNode
from .enums import NodeType


@dataclass(frozen=True)
class NodeView:
    """
    Comprehensive view of a single node with navigation context.

    NodeView provides everything needed to understand a node's position
    and role in the knowledge tree. It includes the node itself plus
    contextual information like breadcrumbs and neighbor counts.

    This view is optimized for:
    - Detail pages showing a specific node
    - LLM context when reasoning about a specific location
    - API responses for single-node queries

    Attributes:
        node: The underlying TreeNode.
        breadcrumb: Tuple of paths from root to this node (inclusive).
        child_count: Number of ACTIVE children (for CATEGORYs only).
        sibling_count: Number of ACTIVE sibling CATEGORYs at same level.

    Properties:
        path: Shortcut to node.path.
        is_category: True if this is a CATEGORY node.
        summary: Formatted string with path and content preview.

    Example:
        >>> view = await semafs.read("root.work.projects")
        >>> print(view.breadcrumb)
        ('root', 'root.work', 'root.work.projects')
        >>> print(view.child_count)
        5
    """
    node: TreeNode
    breadcrumb: Tuple[str, ...]  # Path chain from root to this node
    child_count: int             # Number of ACTIVE children
    sibling_count: int           # Number of ACTIVE sibling CATEGORYs

    @property
    def path(self) -> str:
        """Get the full path of this node."""
        return self.node.path

    @property
    def is_category(self) -> bool:
        """Check if this is a CATEGORY (directory) node."""
        return self.node.node_type == NodeType.CATEGORY

    @property
    def summary(self) -> str:
        """
        Generate a brief summary: path + content preview (100 chars).

        Returns:
            Formatted string like "[path] content preview...".
        """
        content_preview = self.node.content[:100]
        suffix = "..." if len(self.node.content) > 100 else ""
        return f"[{self.path}] {content_preview}{suffix}"


@dataclass(frozen=True)
class TreeView:
    """
    Recursive tree view for exploring hierarchical structure.

    TreeView provides a complete subtree structure suitable for:
    - Directory browsing and exploration
    - Exporting the knowledge tree
    - Understanding overall organization

    The view is depth-limited to prevent performance issues with
    deeply nested trees.

    Attributes:
        node: The TreeNode at this level.
        children: Tuple of TreeViews for each child node.
        depth: Current depth in the tree (root = 0).

    Properties:
        path: Shortcut to node.path.
        total_nodes: Recursive count of all nodes in subtree.
        leaf_count: Recursive count of LEAF nodes only.

    Example:
        >>> tree = await semafs.view_tree("root", max_depth=2)
        >>> print(f"Total: {tree.total_nodes}, Leaves: {tree.leaf_count}")
        Total: 42, Leaves: 35
    """
    node: TreeNode
    children: Tuple["TreeView", ...] = ()
    depth: int = 0  # Depth in tree (root = 0)

    @property
    def path(self) -> str:
        """Get the path of the root node of this subtree."""
        return self.node.path

    @property
    def total_nodes(self) -> int:
        """
        Recursively count all nodes in this subtree.

        Returns:
            Total node count including this node and all descendants.
        """
        return 1 + sum(child.total_nodes for child in self.children)

    @property
    def leaf_count(self) -> int:
        """
        Recursively count LEAF nodes in this subtree.

        Returns:
            Number of LEAF nodes (excluding CATEGORYs).
        """
        if self.node.node_type == NodeType.LEAF:
            return 1
        return sum(child.leaf_count for child in self.children)


@dataclass(frozen=True)
class RelatedNodes:
    """
    Navigation map showing a node's contextual relationships.

    RelatedNodes provides the "neighborhood" around a node, enabling
    LLMs to understand context and make navigation suggestions.
    Think of it as a compass showing what's around the current location.

    This view includes:
    - Parent: Where this node came from
    - Siblings: Other nodes at the same level
    - Children: What's inside (for CATEGORYs)
    - Ancestors: Full path back to root

    Attributes:
        current: NodeView of the focal node.
        parent: NodeView of parent (None for root).
        siblings: Tuple of sibling NodeViews.
        children: Tuple of child NodeViews (empty for LEAFs).
        ancestors: Tuple of ancestor NodeViews (nearest first).

    Properties:
        navigation_summary: Human-readable summary of relationships.

    Example:
        >>> related = await semafs.get_related("root.work.projects")
        >>> print(related.navigation_summary)
        Current: root.work.projects | Parent: root.work | 3 siblings | 5 children
    """
    current: NodeView
    parent: Optional[NodeView] = None
    siblings: Tuple[NodeView, ...] = ()
    children: Tuple[NodeView, ...] = ()
    ancestors: Tuple[NodeView, ...] = ()  # Nearest to farthest

    @property
    def navigation_summary(self) -> str:
        """
        Generate a human-readable navigation summary.

        Returns:
            String describing current location and neighbor counts.
        """
        parts = [f"Current: {self.current.path}"]

        if self.parent:
            parts.append(f"Parent: {self.parent.path}")

        if self.siblings:
            parts.append(f"{len(self.siblings)} siblings")

        if self.children:
            parts.append(f"{len(self.children)} children")

        if self.ancestors:
            parts.append(f"Ancestor depth: {len(self.ancestors)}")

        return " | ".join(parts)


@dataclass(frozen=True)
class StatsView:
    """
    Statistical overview of the entire knowledge base.

    StatsView provides high-level metrics about the knowledge tree,
    useful for:
    - LLM understanding of scale and structure
    - Monitoring and reporting
    - Identifying categories that need attention

    Attributes:
        total_categories: Count of all CATEGORY nodes.
        total_leaves: Count of all LEAF nodes.
        max_depth: Maximum tree depth encountered.
        dirty_categories: Count of categories awaiting maintenance.
        top_categories: Sorted list of (path, child_count) tuples.

    Properties:
        total_nodes: Sum of categories and leaves.
        summary: Human-readable statistics summary.

    Example:
        >>> stats = await semafs.stats()
        >>> print(stats.summary)
        Total 150 nodes (12 categories, 138 leaves), max depth 4
    """
    total_categories: int
    total_leaves: int
    max_depth: int
    dirty_categories: int
    top_categories: Tuple[Tuple[str, int], ...]  # (path, child_count) sorted

    @property
    def total_nodes(self) -> int:
        """Get total node count (categories + leaves)."""
        return self.total_categories + self.total_leaves

    @property
    def summary(self) -> str:
        """
        Generate a human-readable statistics summary.

        Returns:
            Formatted string with key metrics.
        """
        return (
            f"Total {self.total_nodes} nodes "
            f"({self.total_categories} categories, {self.total_leaves} leaves), "
            f"max depth {self.max_depth}"
        )
