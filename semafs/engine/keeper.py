"""Keeper - Maintenance orchestrator."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import uuid4

from ..core.node import Node, NodeStage, NodeType
from ..core.capacity import Budget, Zone
from ..core.ops import RenameOp
from ..core.terminal import TerminalConfig, TerminalGroupMode
from ..core.summary import (
    build_category_meta,
    normalize_category_meta,
    render_category_summary,
)
from ..core.snapshot import Snapshot
from ..core.events import TreeEvent, Persisted
from ..ports.store import NodeStore
from ..ports.factory import UoWFactory
from ..ports.strategy import Strategy
from ..ports.bus import Bus
from ..ports.summarizer import Summarizer
from ..ports.propagation import Policy, Signal, Context
from .executor import Executor
from .guard import (
    PlanGuard,
    GuardReport,
    GuardRejectCode,
    is_name_locked_node,
)
from .resolver import Resolver

logger = logging.getLogger(__name__)


@dataclass
class ReconcileMetrics:
    """Structured observability payload for one reconcile round."""

    node_id: str
    path: str
    zone: str
    allow_rebalance: bool
    has_pending: bool
    rebalance_tried: bool = False
    rebalance_done: bool = False
    promoted: int = 0
    rolled_up: bool = False
    summary_changed: bool = False
    propagated: bool = False
    events: int = 0
    guard_rejects: int = 0
    guard_codes: dict[str, int] = field(default_factory=dict)

    def as_log_payload(self) -> dict:
        return {
            "id": self.node_id,
            "path": self.path,
            "zone": self.zone,
            "allow_rebalance": self.allow_rebalance,
            "has_pending": self.has_pending,
            "rebalance_tried": self.rebalance_tried,
            "rebalance_done": self.rebalance_done,
            "promoted": self.promoted,
            "rolled_up": self.rolled_up,
            "summary_changed": self.summary_changed,
            "propagated": self.propagated,
            "events": self.events,
            "guard_rejects": self.guard_rejects,
            "guard_codes": self.guard_codes,
        }


class Keeper:
    """Maintenance orchestrator (ID-first, summarize-only upward)."""

    def __init__(
        self,
        store: NodeStore,
        uow_factory: UoWFactory,
        bus: Bus,
        strategy: Strategy,
        executor: Executor,
        resolver: Resolver,
        summarizer: Summarizer,
        policy: Policy,
        default_budget: Budget = Budget(),
        terminal_config: TerminalConfig = TerminalConfig(),
        guard: PlanGuard | None = None,
    ):
        self._store = store
        self._uow_factory = uow_factory
        self._bus = bus
        self._strategy = strategy
        self._executor = executor
        self._resolver = resolver
        self._guard = guard or PlanGuard()
        self._summarizer = summarizer
        self._policy = policy
        self._default_budget = default_budget
        self._terminal_config = terminal_config
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
            metrics = ReconcileMetrics(
                node_id=node_id,
                path=snapshot.target.path.value,
                zone=snapshot.zone.name,
                allow_rebalance=allow_rebalance,
                has_pending=snapshot.has_pending,
            )
            if snapshot.zone == Zone.HEALTHY and not snapshot.has_pending:
                self._log_reconcile_metrics(metrics)
                return False

            (
                snapshot,
                rebalance_events,
                plan_summary_changed,
                plan_renamed_nodes,
            ) = await self._rebalance_phase(
                snapshot,
                allow_rebalance=allow_rebalance,
                metrics=metrics,
            )
            emitted_events.extend(rebalance_events)

            snapshot, lifecycle_events = await self._lifecycle_phase(snapshot)
            emitted_events.extend(lifecycle_events)
            metrics.promoted = len(lifecycle_events)

            snapshot, rollup_applied = await self._rollup_phase(snapshot)
            metrics.rolled_up = rollup_applied

            snapshot, summary_changed = await self._summary_phase(
                snapshot,
                plan_summary_changed=plan_summary_changed,
            )
            metrics.summary_changed = summary_changed

            next_node_id, next_signal = await self._propagation_phase(
                snapshot=snapshot,
                signal=signal,
                cause=cause,
                summary_changed=summary_changed,
                plan_renamed_nodes=plan_renamed_nodes,
            )
            metrics.propagated = bool(next_node_id and next_signal)

        if emitted_events:
            await self._publish_events(emitted_events)
        metrics.events = len(emitted_events)
        self._log_reconcile_metrics(metrics)

        if next_node_id and next_signal:
            await self.reconcile(
                next_node_id,
                next_signal,
                cause=cause,
                allow_rebalance=False,
            )
        return True

    async def _rebalance_phase(
        self,
        snapshot: Snapshot,
        *,
        allow_rebalance: bool,
        metrics: ReconcileMetrics | None = None,
    ) -> tuple[Snapshot, list[TreeEvent], bool, bool]:
        """Run structure rebalance phase and plan-level meta updates."""
        if not allow_rebalance:
            return snapshot, [], False, False

        if metrics is not None:
            metrics.rebalance_tried = True

        is_terminal = self._is_terminal(snapshot)
        needs_rebalance = snapshot.has_pending or snapshot.zone in (
            Zone.PRESSURED,
            Zone.OVERFLOW,
        )
        if is_terminal and not self._allow_terminal_group(snapshot):
            needs_rebalance = False
        if not needs_rebalance:
            return snapshot, [], False, False

        raw_plan = await self._strategy.draft(snapshot)
        if not raw_plan:
            return snapshot, [], False, False

        raw_plan, raw_guard_report = self._guard.validate_raw_plan(raw_plan)
        plan = self._resolver.compile(raw_plan, snapshot)
        plan, resolved_guard_report = self._guard.validate_plan(plan)
        plan, snapshot_guard_report = (self._guard.filter_ops_for_snapshot(
            plan, snapshot))
        guard_total, guard_counts = self._guard_metrics(reports=(
            raw_guard_report,
            resolved_guard_report,
            snapshot_guard_report,
        ), )
        if metrics is not None:
            metrics.guard_rejects = guard_total
            metrics.guard_codes = guard_counts
        self._log_guard_metrics(
            path=snapshot.target.path.value,
            total=guard_total,
            counts=guard_counts,
        )
        if (plan.is_empty() and not plan.has_name_update()
                and not plan.has_summary_update()
                and not plan.has_keywords_update()):
            return snapshot, [], False, False

        plan_renamed_nodes = any(isinstance(op, RenameOp) for op in plan.ops)

        async with self._uow_factory.begin() as uow:
            events: list[TreeEvent] = []
            if not plan.is_empty():
                events = self._executor.execute(plan, snapshot, uow)
            plan_summary_changed = self._apply_plan_category_updates(
                plan, snapshot, uow)
            await uow.commit()

        if metrics is not None:
            metrics.rebalance_done = True

        refreshed = await self._build_snapshot(snapshot.target.id)
        return refreshed, events, plan_summary_changed, plan_renamed_nodes

    @staticmethod
    def _guard_metrics(
        *,
        reports: tuple[GuardReport, ...],
    ) -> tuple[int, dict[str, int]]:
        total = sum(report.total_rejects for report in reports)
        counts: dict[str, int] = {}
        for report in reports:
            for code, count in report.counts_by_code().items():
                counts[code] = counts.get(code, 0) + count
        return total, counts

    @staticmethod
    def _log_guard_metrics(
        *,
        path: str,
        total: int,
        counts: dict[str, int],
    ) -> None:
        if total == 0:
            return
        logger.debug(
            "plan_guard_metrics path=%s total_rejects=%d counts=%s",
            path,
            total,
            counts,
        )

    @staticmethod
    def _log_reconcile_metrics(metrics: ReconcileMetrics) -> None:
        logger.debug("reconcile_metrics %s", metrics.as_log_payload())

    async def _lifecycle_phase(
        self,
        snapshot: Snapshot,
    ) -> tuple[Snapshot, list[Persisted]]:
        """Promote pending leaves into active stage."""
        if not snapshot.pending:
            return snapshot, []
        async with self._uow_factory.begin() as uow:
            persisted_events = self._promote_pending(snapshot, uow)
            await uow.commit()
        refreshed = await self._build_snapshot(snapshot.target.id)
        return refreshed, persisted_events

    async def _rollup_phase(
        self,
        snapshot: Snapshot,
    ) -> tuple[Snapshot, bool]:
        """Apply terminal rollup phase when needed."""
        if not self._is_terminal(snapshot):
            return snapshot, False
        rollup_applied = await self._apply_terminal_rollup(snapshot)
        if not rollup_applied:
            return snapshot, False
        return await self._build_snapshot(snapshot.target.id), True

    async def _summary_phase(
        self,
        snapshot: Snapshot,
        *,
        plan_summary_changed: bool,
    ) -> tuple[Snapshot, bool]:
        """Refresh category summary/category_meta when needed."""
        if plan_summary_changed:
            return snapshot, True

        raw_summary, llm_keywords = await self._summarizer.summarize(snapshot)
        meta, new_summary = self._build_snapshot_meta_and_summary(
            snapshot,
            raw_summary,
            llm_keywords,
        )
        logger.debug(
            "category_meta keywords source=%s node=%s",
            meta.get("ext", {}).get("keyword_source"),
            snapshot.target.path.value,
        )
        summary_changed = self._summary_changed(
            snapshot.target.summary,
            new_summary,
        )
        meta_changed = snapshot.target.category_meta != meta
        if not summary_changed and not meta_changed:
            return snapshot, False

        async with self._uow_factory.begin() as uow:
            await self._update_summary(
                snapshot.target.id,
                new_summary,
                meta,
                uow,
            )
            await uow.commit()
        refreshed = await self._build_snapshot(snapshot.target.id)
        return refreshed, summary_changed

    async def _propagation_phase(
        self,
        *,
        snapshot: Snapshot,
        signal: Signal,
        cause: TreeEvent | None,
        summary_changed: bool,
        plan_renamed_nodes: bool,
    ) -> tuple[str | None, Signal | None]:
        """Decide upward propagation target after local reconcile."""
        if not summary_changed and plan_renamed_nodes:
            summary_changed = True
        if not summary_changed or not snapshot.target.parent_id:
            return None, None

        parent = await self._store.get_by_id(snapshot.target.parent_id)
        if not parent:
            return None, None

        ctx = Context(
            event=cause,
            from_path=snapshot.target.path.value,
            to_path=parent.path.value,
            signal=signal,
            snapshot=snapshot,
        )
        step = self._policy.step(ctx)
        logger.debug(
            "propagation: %s -> %s | signal=%.3f -> %.3f | "
            "depth=%d | continue=%s | reason=%s",
            ctx.from_path,
            ctx.to_path,
            signal.value,
            step.signal.value,
            step.signal.depth,
            step.should_continue,
            step.reason,
        )
        if not step.should_continue:
            return None, None
        return parent.id, step.signal

    async def sweep(self, limit: int | None = None) -> int:
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

    async def _update_summary(
        self,
        node_id: str,
        new_summary: str,
        category_meta: dict,
        uow,
    ) -> None:
        node = await self._store.get_by_id(node_id)
        if node:
            updated = node.with_summary(new_summary)
            updated = updated.with_category_meta(category_meta)
            uow.register_dirty(updated)

    async def _publish_events(self, events: list[TreeEvent]) -> None:
        for event in events:
            await self._bus.publish(event)

    def _promote_pending(self, snapshot: Snapshot, uow) -> list[Persisted]:
        events: list[Persisted] = []
        for pending in snapshot.pending:
            active = pending.with_stage(NodeStage.ACTIVE)
            uow.register_dirty(active)
            events.append(
                Persisted(
                    leaf_id=active.id,
                    parent_id=snapshot.target.id,
                    leaf_path=active.path.value,
                    parent_path=snapshot.target.path.value,
                ))
        return events

    def _apply_plan_category_updates(
        self,
        plan,
        snapshot: Snapshot,
        uow,
    ) -> bool:
        """
        Apply plan-level updates for target category.

        Rules:
        - updated_name must match ^[a-z]+$ (single english word)
        - updated_summary must be non-empty after trim
        """
        changed = False
        target = snapshot.target

        if plan.updated_name and plan.updated_name != target.name:
            # Keep top-level entry categories stable (e.g. root.work).
            if target.path.depth <= 1:
                logger.warning(
                    "Skip rename for top-level category %s -> %s",
                    target.path.value,
                    plan.updated_name,
                )
            elif is_name_locked_node(target):
                logger.warning(
                    "plan_guard_reject code=%s message=%s path=%s",
                    GuardRejectCode.SKELETON_RENAME_BLOCKED.value,
                    "Reject updated_name on locked skeleton category",
                    target.path.value,
                )
            else:
                uow.register_rename(target.id, plan.updated_name)
                changed = True

        if plan.updated_summary is not None or plan.updated_keywords:
            meta, normalized = self._build_snapshot_meta_and_summary(
                snapshot,
                plan.updated_summary,
                plan.updated_keywords if plan.updated_keywords else None,
            )
            logger.debug(
                "plan updated_keywords source=%s node=%s",
                meta.get("ext", {}).get("keyword_source"),
                snapshot.target.path.value,
            )
            if (self._summary_changed(target.summary, normalized)
                    or target.category_meta != meta):
                updated = target.with_summary(normalized)
                updated = updated.with_category_meta(meta)
                uow.register_dirty(updated)
                changed = True

        return changed

    def _build_snapshot_meta_and_summary(
        self,
        snapshot: Snapshot,
        raw_summary: str | None,
        preferred_keywords: tuple[str, ...] | None,
    ) -> tuple[dict, str]:
        leaf_texts = tuple(n.content
                           for n in (snapshot.leaves + snapshot.pending)
                           if n.content)
        child_names = tuple(n.name for n in snapshot.subcategories)
        ext_payload = dict(snapshot.target.category_meta.get("ext", {}))
        ext_payload["terminal"] = (snapshot.target.path.depth
                                   >= self._terminal_config.terminal_depth
                                   or bool(ext_payload.get("terminal")))
        ext_payload.setdefault(
            "rollup_window",
            self._terminal_config.rollup_window,
        )
        ext_payload.setdefault(
            "active_raw_limit",
            self._terminal_config.active_raw_limit,
        )
        placement = self._latest_placement_payload(snapshot)
        if placement:
            ext_payload["placement_source"] = str(
                placement.get("source", "none"))
            ext_payload["placement_target"] = str(
                placement.get("target_path", snapshot.target.path.value))
            ext_payload["placement_reasoning"] = str(
                placement.get("reasoning", ""))[:200]
            ext_payload["placement_confidence"] = (
                self._placement_confidence(placement))
        existing_keywords = tuple(
            str(v).strip()
            for v in snapshot.target.category_meta.get("keywords", [])
            if isinstance(v, str) and str(v).strip())
        effective_keywords = (preferred_keywords if preferred_keywords
                              is not None else existing_keywords)

        meta = build_category_meta(
            raw_summary=raw_summary,
            leaf_texts=leaf_texts,
            child_names=child_names,
            keywords=effective_keywords if effective_keywords else None,
            ext=ext_payload,
        )
        normalized = normalize_category_meta(meta)
        return normalized, render_category_summary(normalized)

    @staticmethod
    def _latest_placement_payload(snapshot: Snapshot) -> dict | None:
        candidates = sorted(
            snapshot.pending + snapshot.leaves,
            key=Keeper._leaf_order_key,
            reverse=True,
        )
        for node in candidates:
            payload = node.payload or {}
            placement = payload.get("_placement")
            if isinstance(placement, dict):
                return placement
        return None

    @staticmethod
    def _placement_confidence(placement: dict) -> float:
        steps = placement.get("steps", [])
        if isinstance(steps, list):
            for step in reversed(steps):
                if not isinstance(step, dict):
                    continue
                value = step.get("confidence")
                try:
                    conf = float(value)
                except (TypeError, ValueError):
                    continue
                return min(1.0, max(0.0, conf))
        return 0.0

    def _is_terminal(self, snapshot: Snapshot) -> bool:
        return self._is_terminal_node(snapshot.target)

    def _is_terminal_node(self, node) -> bool:
        ext = node.category_meta.get("ext", {})
        if bool(ext.get("terminal")):
            return True
        return node.path.depth >= self._terminal_config.terminal_depth

    def _allow_terminal_group(self, snapshot: Snapshot) -> bool:
        if self._terminal_config.group_mode == TerminalGroupMode.DISABLED:
            return False
        if self._terminal_config.group_mode != TerminalGroupMode.HIGH_GAIN:
            return False
        required_gain_count = snapshot.budget.hard + max(
            2, snapshot.budget.soft // 2)
        return (snapshot.zone == Zone.OVERFLOW
                and snapshot.total_children >= required_gain_count
                and len(snapshot.pending) >= 2)

    async def _apply_terminal_rollup(self, snapshot: Snapshot) -> bool:
        """
        Roll up excessive raw leaves under terminal categories.

        Strategy:
        - Keep latest `active_raw_limit` leaves active
        - Archive older leaves in batches
        - Create one rollup leaf that summarizes archived batch
        """
        if len(snapshot.leaves) < self._terminal_config.rollup_trigger_count:
            return False

        ordered = sorted(snapshot.leaves, key=self._leaf_order_key)
        overflow = len(ordered) - self._terminal_config.active_raw_limit
        if overflow < self._terminal_config.min_rollup_batch:
            return False

        batch = ordered[:overflow]
        rollup_content = self._build_rollup_content(batch, snapshot.target)
        rollup_name = (f"rollup_{self._terminal_config.rollup_window}_"
                       f"{uuid4().hex[:6]}")
        rollup_leaf = Node.create_leaf(
            parent_id=snapshot.target.id,
            parent_path=snapshot.target.path.value,
            name=rollup_name,
            content=rollup_content,
            payload={
                "rollup": True,
                "window": self._terminal_config.rollup_window,
                "source_count": len(batch),
                "source_ids": [leaf.id for leaf in batch],
                "rolled_at": datetime.utcnow().isoformat() + "Z",
            },
            stage=NodeStage.ACTIVE,
        )

        async with self._uow_factory.begin() as uow:
            uow.register_new(rollup_leaf)
            for leaf in batch:
                uow.register_removed(leaf.id)
            # Persist terminal bookkeeping in category meta.ext
            ext = dict(snapshot.target.category_meta.get("ext", {}))
            ext["last_rollup_count"] = len(batch)
            ext["last_rollup_window"] = self._terminal_config.rollup_window
            ext["last_rollup_at"] = datetime.utcnow().isoformat() + "Z"
            meta = dict(snapshot.target.category_meta)
            meta["ext"] = ext
            updated_target = snapshot.target.with_category_meta(meta)
            uow.register_dirty(updated_target)
            await uow.commit()
        return True

    @staticmethod
    def _leaf_order_key(node: Node) -> tuple[str, str]:
        payload = node.payload or {}
        stamp = str(
            payload.get("_ingested_at") or payload.get("ingested_at") or "")
        return (stamp, node.name)

    @staticmethod
    def _build_rollup_content(leaves: list[Node], target: Node) -> str:
        snippets = []
        for leaf in leaves[:20]:
            text = (leaf.content or "").strip().replace("\n", " ")
            if not text:
                continue
            snippets.append(f"- {text[:120]}")
        joined = "\n".join(snippets) if snippets else "- (empty batch)"
        return (f"Rollup for {target.path.value}\n"
                f"items: {len(leaves)}\n"
                f"window: auto-{datetime.utcnow().date().isoformat()}\n"
                f"{joined}")[:2000]

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
