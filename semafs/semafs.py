from __future__ import annotations
import asyncio
import logging
from typing import Optional
from .core.node import Node, NodePath, NodeType, NodeStage
from .core.capacity import Budget
from .core.naming import PathAllocator
from .core.terminal import TerminalConfig
from .core.views import NodeView, TreeView, RelatedNodes, StatsView
from .ports.store import NodeStore
from .ports.factory import UoWFactory
from .ports.strategy import Strategy
from .ports.bus import Bus
from .ports.placer import Placer
from .ports.summarizer import Summarizer
from .ports.propagation import Policy
from .engine.keeper import Keeper
from .engine.executor import Executor
from .engine.guard import PlanGuard
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
            bus: Bus,
            strategy: Strategy,
            placer: Placer,
            summarizer: Summarizer,
            policy: Policy,
            budget: Budget = Budget(),
            terminal_config: TerminalConfig = TerminalConfig(),
    ):
        self._store = store
        self._uow_factory = uow_factory
        self._bus = bus
        self._budget = budget

        allocator = PathAllocator()
        guard = PlanGuard()
        self._executor = Executor()
        self._resolver = Resolver(allocator=allocator)
        self._keeper = Keeper(
            store=store,
            uow_factory=uow_factory,
            bus=bus,
            strategy=strategy,
            executor=self._executor,
            resolver=self._resolver,
            guard=guard,
            summarizer=summarizer,
            policy=policy,
            default_budget=budget,
            terminal_config=terminal_config,
        )
        self._intake = Intake(placer=placer, store=store, allocator=allocator)
        self._pulse = Pulse(bus=bus, policy=policy, keeper=self._keeper)
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

        (
            parent_node,
            sibling_nodes,
            children_nodes,
            ancestor_nodes,
        ) = await asyncio.gather(
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
        node_ids = tuple(await self._store.all_node_ids())
        if not node_ids:
            return StatsView(
                total_categories=0,
                total_leaves=0,
                max_depth=0,
                dirty_categories=0,
                top_categories=(),
            )

        nodes = await asyncio.gather(
            *[self._store.get_by_id(node_id) for node_id in node_ids])
        active_nodes = tuple(node for node in nodes if node is not None)
        categories = tuple(node for node in active_nodes
                           if node.node_type == NodeType.CATEGORY)
        leaves = tuple(node for node in active_nodes
                       if node.node_type == NodeType.LEAF)
        max_depth = max((node.path.depth for node in active_nodes), default=0)

        child_lists = await asyncio.gather(
            *[self._store.list_children(node.id) for node in categories])
        dirty_categories = 0
        ranked_categories: list[tuple[str, int]] = []
        for category, children in zip(categories, child_lists, strict=False):
            child_count = len(children)
            ranked_categories.append((category.path.value, child_count))
            if any(child.stage == NodeStage.PENDING for child in children):
                dirty_categories += 1
        top_categories = tuple(
            sorted(ranked_categories, key=lambda item: item[1],
                   reverse=True)[:5])

        return StatsView(
            total_categories=len(categories),
            total_leaves=len(leaves),
            max_depth=max_depth,
            dirty_categories=dirty_categories,
            top_categories=top_categories,
        )

    async def sweep(self, limit: int | None = None) -> int:
        """Scan overflow categories and reconcile them."""
        return await self._keeper.sweep(limit=limit)

    async def apply_skeleton(
        self,
        skeleton: dict | list[str] | tuple[str, ...] | str,
        *,
        source: str = "manual",
    ) -> int:
        """
        Apply skeleton categories and lock their names.

        Skeleton categories can still update summary/meta, but category names
        are protected from rename operations.
        """
        paths = self._collect_skeleton_paths(skeleton)
        if not paths:
            return 0

        changed = 0
        async with self._uow_factory.begin() as uow:
            staged_by_path: dict[str, Node] = {}
            for path in paths:
                existing = staged_by_path.get(path)
                if existing is None:
                    existing = await self._store.get_by_path(path)

                if existing:
                    if existing.node_type != NodeType.CATEGORY:
                        raise ValueError(
                            "Skeleton path conflicts with leaf node: "
                            f"{path}")
                    locked = existing.with_skeleton(True)
                    payload = dict(locked.payload)
                    payload["skeleton_source"] = source
                    locked = locked.with_payload(payload)
                    if locked != existing:
                        uow.register_dirty(locked)
                        changed += 1
                        staged_by_path[path] = locked
                    continue

                parent_path = NodePath(path).parent_str
                parent = staged_by_path.get(parent_path)
                if parent is None:
                    parent = await self._store.get_by_path(parent_path)
                if not parent:
                    raise ValueError(
                        f"Skeleton parent not found: {parent_path}")
                if parent.node_type != NodeType.CATEGORY:
                    raise ValueError("Skeleton parent is not a category: "
                                     f"{parent_path}")
                name = NodePath(path).name
                summary = f"Skeleton category: {name}"
                node = Node.create_category(
                    parent_id=parent.id,
                    parent_path=parent.path.value,
                    name=name,
                    summary=summary,
                    category_meta={},
                    payload={"skeleton_source": source},
                    skeleton=True,
                    name_editable=False,
                )
                uow.register_new(node)
                staged_by_path[path] = node
                changed += 1
            await uow.commit()
        return changed

    def _collect_skeleton_paths(
        self,
        skeleton: dict | list[str] | tuple[str, ...] | str,
    ) -> tuple[str, ...]:
        paths: set[str] = set()
        if isinstance(skeleton, str):
            paths.add(self._normalize_skeleton_path(skeleton))
        elif isinstance(skeleton, (list, tuple)):
            for item in skeleton:
                if not isinstance(item, str):
                    raise ValueError("Skeleton path list must contain strings")
                paths.add(self._normalize_skeleton_path(item))
        elif isinstance(skeleton, dict):
            root_tree = skeleton
            if ("root" in skeleton and isinstance(skeleton.get("root"), dict)
                    and len(skeleton) == 1):
                root_tree = skeleton["root"]
            self._walk_skeleton_tree("root", root_tree, paths)
        else:
            raise ValueError("Unsupported skeleton payload type")

        return tuple(
            sorted(
                (p for p in paths if p != "root"),
                key=lambda p: p.count("."),
            ))

    def _walk_skeleton_tree(
        self,
        parent_path: str,
        tree: dict,
        paths: set[str],
    ) -> None:
        for raw_name, children in tree.items():
            if not isinstance(raw_name, str):
                raise ValueError("Skeleton category name must be string")
            name = Node.normalize_name(raw_name, fallback_prefix="category")
            path = NodePath.from_parent_and_name(parent_path, name).value
            paths.add(path)
            if children is None:
                continue
            if not isinstance(children, dict):
                raise ValueError("Skeleton tree child must be dict or null: "
                                 f"{path}")
            self._walk_skeleton_tree(path, children, paths)

    @staticmethod
    def _normalize_skeleton_path(path: str) -> str:
        cleaned = path.strip()
        if not cleaned:
            raise ValueError("Skeleton path cannot be empty")
        if cleaned != "root" and not cleaned.startswith("root."):
            cleaned = f"root.{cleaned}"
        return NodePath(cleaned).value
