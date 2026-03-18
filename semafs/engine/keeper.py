"""Keeper - Maintenance orchestrator."""

import asyncio
import logging
from typing import Optional

from ..core.node import NodeStage, NodeType
from ..core.capacity import Budget, Zone
from ..core.snapshot import Snapshot
from ..core.events import TreeEvent
from ..ports.store import NodeStore
from ..ports.factory import UoWFactory
from ..ports.strategy import Strategy
from ..ports.bus import EventBus
from ..ports.summarizer import Summarizer
from ..ports.propagation import Policy, Signal, Context
from .executor import Executor
from .resolver import Resolver

logger = logging.getLogger(__name__)


class Keeper:
    """Maintenance orchestrator (ID-first, summarize-only upward)."""

    def __init__(
            self,
            store: NodeStore,
            uow_factory: UoWFactory,
            bus: EventBus,
            strategy: Strategy,
            executor: Executor,
            resolver: Resolver,
            summarizer: Summarizer,
            policy: Policy,
            default_budget: Budget = Budget(),
    ):
        self._store = store
        self._uow_factory = uow_factory
        self._bus = bus
        self._strategy = strategy
        self._executor = executor
        self._resolver = resolver
        self._summarizer = summarizer
        self._policy = policy
        self._default_budget = default_budget
        self._locks: dict[str, asyncio.Lock] = {}

    async def reconcile(
        self,
        node_id: str,
        signal: Signal,
        cause: TreeEvent | None = None,
        *,
        allow_rebalance: bool = True,
    ) -> bool:
        emitted_events: list[TreeEvent] = []
        next_node_id: str | None = None
        next_signal: Signal | None = None

        lock = self._locks.setdefault(node_id, asyncio.Lock())
        async with lock:
            snapshot = await self._build_snapshot(node_id)
            if snapshot.zone == Zone.HEALTHY and not snapshot.has_pending:
                return False

            # v2.1.4 rule: only origin hop can rebalance structure.
            if allow_rebalance:
                needs_rebalance = snapshot.has_pending or snapshot.zone in (
                    Zone.PRESSURED,
                    Zone.OVERFLOW,
                )
                if needs_rebalance:
                    raw_plan = await self._strategy.draft(snapshot)
                    if raw_plan:
                        plan = self._resolver.compile(raw_plan, snapshot)
                        if not plan.is_empty():
                            async with self._uow_factory.begin() as uow:
                                events = self._executor.execute(
                                    plan, snapshot, uow)
                                await uow.commit()
                            emitted_events.extend(events)
                            snapshot = await self._build_snapshot(node_id)

            new_summary = await self._summarizer.summarize(snapshot)
            summary_changed = self._summary_changed(snapshot.target.summary,
                                                    new_summary)
            if summary_changed:
                async with self._uow_factory.begin() as uow:
                    await self._update_summary(node_id, new_summary, uow)
                    await uow.commit()

                if snapshot.target.parent_id:
                    parent = await self._store.get_by_id(
                        snapshot.target.parent_id)
                    if parent:
                        ctx = Context(
                            event=cause,
                            from_path=snapshot.target.path.value,
                            to_path=parent.path.value,
                            signal=signal,
                            snapshot=snapshot,
                        )
                        step = self._policy.step(ctx)
                        logger.debug(
                            "propagation hop: %s -> %s | signal=%.3f -> %.3f | "
                            "depth=%d | continue=%s | reason=%s",
                            ctx.from_path,
                            ctx.to_path,
                            signal.value,
                            step.signal.value,
                            step.signal.depth,
                            step.should_continue,
                            step.reason,
                        )
                        if step.should_continue:
                            next_node_id = parent.id
                            next_signal = step.signal

        if emitted_events:
            await self._publish_events(emitted_events)

        if next_node_id and next_signal:
            await self.reconcile(
                next_node_id,
                next_signal,
                cause=cause,
                allow_rebalance=False,
            )
        return True

    async def sweep_overloaded(self, limit: int | None = None) -> int:
        node_ids = await self._find_overloaded_nodes(limit=limit)
        processed = 0
        for node_id in node_ids:
            scan_signal = await self._scan_signal(node_id)
            if await self.reconcile(node_id, scan_signal,
                                    allow_rebalance=True):
                processed += 1
        return processed

    async def _build_snapshot(self, node_id: str) -> Snapshot:
        target = await self._store.get_by_id(node_id)
        if not target:
            raise ValueError(f"Category not found: {node_id}")

        children = await self._store.list_children(node_id)
        siblings = await self._store.list_siblings(node_id)
        ancestors = await self._store.get_ancestors(node_id, max_depth=3)
        all_paths = await self._store.all_paths()

        leaves = []
        subcategories = []
        pending = []
        for child in children:
            if child.stage == NodeStage.PENDING:
                pending.append(child)
            elif child.node_type == NodeType.LEAF:
                leaves.append(child)
            else:
                subcategories.append(child)

        return Snapshot(
            target=target,
            leaves=tuple(leaves),
            subcategories=tuple(subcategories),
            pending=tuple(pending),
            siblings=tuple(siblings),
            ancestors=tuple(ancestors),
            budget=self._default_budget,
            used_paths=all_paths,
        )

    def _summary_changed(self, old: Optional[str], new: str) -> bool:
        if old is None:
            return True
        return old.strip() != new.strip()

    async def _update_summary(self, node_id: str, new_summary: str,
                              uow) -> None:
        node = await self._store.get_by_id(node_id)
        if node:
            uow.register_dirty(node.with_summary(new_summary))

    async def _publish_events(self, events: list[TreeEvent]) -> None:
        for event in events:
            await self._bus.publish(event)

    async def _scan_signal(self, node_id: str) -> Signal:
        origin = await self._store.canonical_path(node_id) or node_id
        return Signal(
            value=1.0,
            origin=origin,
            event_type="OverloadScan",
            payload={"source": "sweep"},
        )

    async def _find_overloaded_nodes(
        self,
        limit: int | None = None,
    ) -> tuple[str, ...]:
        all_ids = list(await self._store.all_node_ids())
        if not all_ids:
            return ()

        paths = await asyncio.gather(
            *[self._store.canonical_path(nid) for nid in all_ids])
        ordered_ids = [
            nid for nid, _ in sorted(
                zip(all_ids, paths, strict=False),
                key=lambda item: (item[1] or "").count("."),
                reverse=True,
            )
        ]

        nodes = await asyncio.gather(
            *[self._store.get_by_id(nid) for nid in ordered_ids])
        category_ids = [
            nid for nid, node in zip(ordered_ids, nodes, strict=False)
            if node and node.node_type == NodeType.CATEGORY
        ]
        if not category_ids:
            return ()

        children_list = await asyncio.gather(
            *[self._store.list_children(nid) for nid in category_ids])
        overloaded: list[str] = []
        for nid, children in zip(category_ids, children_list, strict=False):
            if self._default_budget.is_overflow(len(children)):
                overloaded.append(nid)
                if limit is not None and len(overloaded) >= limit:
                    break
        return tuple(overloaded)
