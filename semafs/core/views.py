"""View layer - Structured query views for the knowledge tree."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Tuple

from .node import Node, NodeType


@dataclass(frozen=True)
class NodeView:
    """Single node with navigation context."""

    node: Node
    breadcrumb: Tuple[str, ...]
    child_count: int
    sibling_count: int

    @property
    def path(self) -> str:
        return self.node.path.value

    @property
    def is_category(self) -> bool:
        return self.node.node_type == NodeType.CATEGORY

    @property
    def summary(self) -> str:
        content = self.node.content or self.node.summary or ""
        preview = content[:100]
        suffix = "..." if len(content) > 100 else ""
        return f"[{self.path}] {preview}{suffix}"


@dataclass(frozen=True)
class TreeView:
    """Recursive tree structure."""

    node: Node
    children: Tuple["TreeView", ...] = ()
    depth: int = 0

    @property
    def path(self) -> str:
        return self.node.path.value

    @property
    def total_nodes(self) -> int:
        return 1 + sum(c.total_nodes for c in self.children)

    @property
    def leaf_count(self) -> int:
        if self.node.node_type == NodeType.LEAF:
            return 1
        return sum(c.leaf_count for c in self.children)


@dataclass(frozen=True)
class RelatedNodes:
    """Navigation map around a node."""

    current: NodeView
    parent: Optional[NodeView] = None
    siblings: Tuple[NodeView, ...] = ()
    children: Tuple[NodeView, ...] = ()
    ancestors: Tuple[NodeView, ...] = ()

    @property
    def navigation_summary(self) -> str:
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
    """Knowledge base statistics."""

    total_categories: int
    total_leaves: int
    max_depth: int
    dirty_categories: int
    top_categories: Tuple[Tuple[str, int], ...]

    @property
    def total_nodes(self) -> int:
        return self.total_categories + self.total_leaves

    @property
    def summary(self) -> str:
        return (
            f"Total {self.total_nodes} nodes "
            f"({self.total_categories} categories, {self.total_leaves} leaves), "
            f"max depth {self.max_depth}"
        )
