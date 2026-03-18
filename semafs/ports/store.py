"""NodeStore - Storage operations protocol."""

from typing import Protocol, runtime_checkable

from ..core.node import Node


@runtime_checkable
class NodeStore(Protocol):
    """Node storage interface."""

    async def get_by_id(self, node_id: str) -> Node | None:
        """Get node by ID."""
        ...

    async def get_by_path(self, path: str) -> Node | None:
        """Get node by canonical path."""
        ...

    async def resolve_path(self, path: str) -> str | None:
        """Resolve canonical path to node ID."""
        ...

    async def canonical_path(self, node_id: str) -> str | None:
        """Resolve node ID to canonical path."""
        ...

    async def save(self, node: Node) -> None:
        """Save or update node."""
        ...

    async def list_children(self, node_id: str) -> list[Node]:
        """List all active children of a node."""
        ...

    async def list_siblings(self, node_id: str) -> list[Node]:
        """List all siblings of a node (same parent)."""
        ...

    async def get_ancestors(
        self,
        node_id: str,
        max_depth: int = 3,
    ) -> list[Node]:
        """Get ancestor chain (nearest to farthest)."""
        ...

    async def all_node_ids(self) -> frozenset[str]:
        """Get all active node IDs."""
        ...

    async def all_paths(self) -> frozenset[str]:
        """Get all active canonical paths."""
        ...
