"""Intake - Write pipeline for new content."""

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from ..core.node import Node, NodeStage
from ..core.placement import PlacementRoute
from ..core.naming import PathAllocator
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

    def __init__(
        self,
        placer: Placer,
        store: NodeStore,
        allocator: PathAllocator | None = None,
    ):
        self.placer = placer
        self._store = store
        self._allocator = allocator or PathAllocator()

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
        routed = hint is None
        reasoning = None
        route: PlacementRoute | None = None
        if hint:
            target_path = hint
        else:
            route = await self.placer.place(
                content,
                start_path="root",
            )
            target_path = route.target_path
            reasoning = route.reasoning or None

        if not target_path:
            target_path = "root"
        target_id = await self._store.resolve_path(target_path)
        if not target_id:
            raise ValueError(f"Target category not found: {target_path}")
        parent_path = await self._store.canonical_path(target_id)
        if not parent_path:
            raise ValueError(
                f"Target category has no canonical path: {target_id}")

        # Generate placeholder name; semantic rename happens in maintenance.
        base_name = self._placeholder_name()
        name = await self._ensure_unique_name(target_id, base_name)

        # Create pending leaf
        merged_payload = dict(payload or {})
        merged_payload.setdefault(
            "_ingested_at",
            datetime.now(timezone.utc).isoformat(),
        )
        merged_payload["_placement"] = self._build_placement_payload(
            hint=hint,
            target_path=target_path,
            route=route,
        )
        leaf = Node.create_leaf(
            parent_id=target_id,
            parent_path=parent_path,
            name=name,
            content=content,
            payload=merged_payload,
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
            routed=routed,
            reasoning=reasoning,
        )

        return WriteResult(leaf_id=leaf.id, placed=placed)

    async def _ensure_unique_name(self, parent_id: str, base_name: str) -> str:
        existing = await self._store.list_children(parent_id)
        names = {n.name for n in existing}
        return self._allocator.allocate_name(
            raw_name=base_name,
            used_names=names,
            fallback_prefix="leaf",
        )

    def _placeholder_name(self) -> str:
        """Build write-time stable placeholder name."""
        return f"leaf_{uuid4().hex[:6]}"

    @staticmethod
    def _build_placement_payload(
        *,
        hint: str | None,
        target_path: str,
        route: PlacementRoute | None,
    ) -> dict:
        if route is None:
            return {
                "source": "hint" if hint else "default",
                "target_path": target_path,
                "reasoning": "user hint" if hint else "default root route",
                "steps": [],
            }
        steps = []
        for step in route.steps[:10]:
            steps.append({
                "depth": step.depth,
                "current_path": step.current_path,
                "action": step.decision.action.value,
                "target_child": step.decision.target_child,
                "confidence": step.decision.confidence,
                "reasoning": step.decision.reasoning,
            })
        return {
            "source": "llm_recursive",
            "target_path": route.target_path,
            "reasoning": route.reasoning,
            "steps": steps,
        }
