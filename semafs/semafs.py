"""SemaFS - Main facade for the semantic filesystem."""

from __future__ import annotations
import asyncio
import logging
from typing import Optional

from .core.node import Node, NodePath, NodeType
from .core.capacity import Budget
from .core.views import NodeView, TreeView, RelatedNodes, StatsView
from .ports.store import NodeStore
from .ports.factory import UoWFactory
from .ports.strategy import Strategy
from .ports.bus import EventBus
from .ports.placer import Placer
from .ports.summarizer import Summarizer
from .ports.propagation import Policy
from .engine.keeper import Keeper
from .engine.executor import Executor
from .engine.resolver import Resolver
from .engine.intake import Intake
from .engine.pulse import Pulse

logger = logging.getLogger(__name__)


class SemaFS:
    """Main facade for the semantic filesystem."""

    def __init__(
            self,
            store: NodeStore,
            uow_factory: UoWFactory,
            bus: EventBus,
            strategy: Strategy,
            placer: Placer,
            summarizer: Summarizer,
            policy: Policy,
            budget: Budget = Budget(),
    ):
        self._store = store
        self._uow_factory = uow_factory
        self._bus = bus
        self._budget = budget

        # Engine components
        self._executor = Executor()
        self._resolver = Resolver()
        self._keeper = Keeper(
            store=store,
            uow_factory=uow_factory,
            bus=bus,
            strategy=strategy,
            executor=self._executor,
            resolver=self._resolver,
            summarizer=summarizer,
            policy=policy,
            default_budget=budget,
        )
        self._intake = Intake(placer=placer, store=store)
        self._pulse = Pulse(bus=bus, policy=policy, keeper=self._keeper)

        # Wire up event subscriptions
        self._pulse.subscribe()

    async def write(
        self,
        content: str,
        hint: str | None = None,
        payload: dict | None = None,
    ) -> str:
        """Write new content to the tree."""
        async with self._uow_factory.begin() as uow:
            result = await self._intake.write(content, hint, uow, payload)
            await uow.commit()
        await self._bus.publish(result.placed)
        return result.leaf_id

    async def read(self, path: str) -> Optional[NodeView]:
        """Get single node with navigation context."""
        node = await self._store.get_by_path(path)
        if not node:
            return None

        children, siblings, ancestors = await asyncio.gather(
            self._store.list_children(node.id),
            self._store.list_siblings(node.id),
            self._store.get_ancestors(node.id, max_depth=3),
        )

        breadcrumb = tuple(a.path.value
                           for a in reversed(ancestors)) + (path, )

        return NodeView(
            node=node,
            breadcrumb=breadcrumb,
            child_count=len(children),
            sibling_count=len(siblings),
        )

    async def list(self, path: str) -> list[NodeView]:
        """List direct children of a category."""
        node = await self._store.get_by_path(path)
        if not node:
            return []
        children = await self._store.list_children(node.id)
        views = []
        for child in children:
            view = await self.read(child.path.value)
            if view:
                views.append(view)
        return sorted(views, key=lambda v: v.path)

    async def tree(self,
                   path: str = "root",
                   max_depth: int = 3) -> Optional[TreeView]:
        """Get recursive tree structure."""
        node = await self._store.get_by_path(path)
        if not node:
            return None
        return await self._build_tree(node, depth=0, max_depth=max_depth)

    async def _build_tree(self, node: Node, depth: int,
                          max_depth: int) -> TreeView:
        """Recursively build TreeView."""
        children_views = ()
        if node.node_type == NodeType.CATEGORY and depth < max_depth:
            children = await self._store.list_children(node.id)
            children_views = tuple([
                await self._build_tree(c, depth + 1, max_depth)
                for c in children
            ])
        return TreeView(node=node, children=children_views, depth=depth)

    async def related(self, path: str) -> Optional[RelatedNodes]:
        """Get navigation map around a node."""
        current_view = await self.read(path)
        if not current_view:
            return None

        node = current_view.node
        np = NodePath(path)

        parent_node, sibling_nodes, children_nodes, ancestor_nodes = await asyncio.gather(
            self._store.get_by_path(np.parent_str) if np.parent else None,
            self._store.list_siblings(node.id),
            self._store.list_children(node.id)
            if node.node_type == NodeType.CATEGORY else [],
            self._store.get_ancestors(node.id),
        )

        parent_view = await self.read(parent_node.path.value
                                      ) if parent_node else None

        sibling_views = []
        for sib in sibling_nodes:
            view = await self.read(sib.path.value)
            if view:
                sibling_views.append(view)

        children_views = []
        for child in children_nodes:
            view = await self.read(child.path.value)
            if view:
                children_views.append(view)

        ancestor_views = []
        for anc in ancestor_nodes:
            view = await self.read(anc.path.value)
            if view:
                ancestor_views.append(view)

        return RelatedNodes(
            current=current_view,
            parent=parent_view,
            siblings=tuple(sibling_views),
            children=tuple(children_views),
            ancestors=tuple(ancestor_views),
        )

    async def stats(self) -> StatsView:
        """Get knowledge base statistics."""
        # Simplified stats — just return placeholder
        return StatsView(
            total_categories=0,
            total_leaves=0,
            max_depth=0,
            dirty_categories=0,
            top_categories=(),
        )

    async def sweep(self, limit: int | None = None) -> int:
        """Scan overflow categories and reconcile them."""
        return await self._keeper.sweep_overloaded(limit=limit)

    async def maintain(self, limit: int | None = None) -> int:
        """Backward-compatible alias of `sweep`."""
        return await self.sweep(limit=limit)
