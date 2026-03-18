"""Intake - Write pipeline for new content."""

from dataclasses import dataclass

from ..core.node import Node, NodeStage
from ..core.events import Placed
from ..ports.factory import UnitOfWork
from ..ports.placer import Placer
from ..ports.store import NodeStore


@dataclass(frozen=True)
class WriteResult:
    """Staged write result produced by Intake."""

    leaf_id: str
    placed: Placed


class Intake:
    """Write pipeline - routes and stages new content."""

    def __init__(self, placer: Placer, store: NodeStore):
        self.placer = placer
        self._store = store

    async def write(
        self,
        content: str,
        hint: str | None,
        uow: UnitOfWork,
        payload: dict | None = None,
    ) -> WriteResult:
        """
        Write new content to the tree.

        Args:
            content: Content to write
            hint: Optional path hint (if None, uses placer to route)
            uow: Unit of Work for transaction
            payload: Optional metadata

        Returns:
            Staged write result with event payload
        """
        # Determine target path and resolve to stable identity.
        target_path = hint if hint else await self.placer.place(content, hint)
        target_id = await self._store.resolve_path(target_path)
        if not target_id:
            raise ValueError(f"Target category not found: {target_path}")
        parent_path = await self._store.canonical_path(target_id)
        if not parent_path:
            raise ValueError(f"Target category has no canonical path: {target_id}")

        # Generate leaf name under resolved parent.
        suffix = content[:24].strip().lower().replace(" ", "_")
        suffix = "".join(c for c in suffix if c.isalnum() or c == "_")
        base_name = suffix or "note"
        name = await self._ensure_unique_name(target_id, base_name)

        # Create pending leaf
        leaf = Node.create_leaf(
            parent_id=target_id,
            parent_path=parent_path,
            name=name,
            content=content,
            payload=payload or {},
            stage=NodeStage.PENDING,
        )

        # Register with UoW
        uow.register_new(leaf)

        # Build event envelope; caller publishes after successful commit.
        placed = Placed(
            leaf_id=leaf.id,
            parent_id=target_id,
            leaf_path=leaf.path.value,
            parent_path=parent_path,
            routed=hint is None,
            reasoning=None,
        )

        return WriteResult(leaf_id=leaf.id, placed=placed)

    async def _ensure_unique_name(self, parent_id: str, base_name: str) -> str:
        existing = await self._store.list_children(parent_id)
        names = {n.name for n in existing}
        if base_name not in names:
            return base_name
        i = 1
        while f"{base_name}_{i}" in names:
            i += 1
        return f"{base_name}_{i}"
