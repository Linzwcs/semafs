"""SnapshotBuilder - Builds immutable snapshots for maintenance operations."""

from typing import Protocol, runtime_checkable

from ..core.capacity import Budget
from ..core.node import Node, NodeType, NodeStage
from ..core.snapshot import Snapshot


@runtime_checkable
class Reader(Protocol):
    """Minimal read interface for snapshot building."""

    async def get_by_id(self, node_id: str) -> Node | None: ...
    async def list_children(self, node_id: str) -> list[Node]: ...
    async def list_siblings(self, node_id: str) -> list[Node]: ...
    async def get_ancestors(self, node_id: str, max_depth: int = 3) -> list[Node]: ...
    async def all_paths(self) -> frozenset[str]: ...


class SnapshotBuilder:
    """
    Builds Snapshot from a Reader interface.

    Decoupled from Keeper to:
    1. Enable transaction-aware snapshot building (uow.reader)
    2. Allow independent testing
    3. Reduce Keeper complexity
    """

    def __init__(self, budget: Budget):
        self._budget = budget

    async def build(self, reader: Reader, node_id: str) -> Snapshot | None:
        """
        Build snapshot for a category node.

        Args:
            reader: Read interface (store or uow.reader)
            node_id: Target category ID

        Returns:
            Snapshot or None if node not found/not a category
        """
        target = await reader.get_by_id(node_id)
        if not target or target.node_type != NodeType.CATEGORY:
            return None

        # Sequential fetch to avoid SQLite threading issues
        children = await reader.list_children(node_id)
        siblings = await reader.list_siblings(node_id)
        ancestors = await reader.get_ancestors(node_id, max_depth=3)
        used_paths = await reader.all_paths()

        # Partition children by type and stage
        leaves: list[Node] = []
        subcategories: list[Node] = []
        pending: list[Node] = []
        cold_leaves: list[Node] = []

        for child in children:
            if child.node_type == NodeType.CATEGORY:
                subcategories.append(child)
            elif child.stage == NodeStage.PENDING:
                pending.append(child)
            elif child.stage == NodeStage.COLD:
                cold_leaves.append(child)
            else:
                leaves.append(child)

        return Snapshot(
            target=target,
            leaves=tuple(leaves),
            subcategories=tuple(subcategories),
            pending=tuple(pending),
            siblings=tuple(siblings),
            ancestors=tuple(ancestors),
            budget=self._budget,
            used_paths=used_paths,
            cold_leaves=tuple(cold_leaves),
        )
