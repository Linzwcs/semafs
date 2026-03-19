"""Phase runners - independent components for maintenance orchestration."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from ..core.capacity import Zone
from ..core.events import TreeEvent, Persisted
from ..core.node import Node, NodeStage, NodeType
from ..core.ops import Plan, RenameOp
from ..core.snapshot import Snapshot
from ..core.summary import (
    build_category_meta,
    normalize_category_meta,
    render_category_summary,
)
from ..core.terminal import TerminalConfig, TerminalGroupMode, TerminalPolicy
from ..ports.factory import UoWFactory, UnitOfWork
from ..ports.propagation import Context, Policy, Signal
from ..ports.store import NodeStore
from ..ports.strategy import Strategy
from ..ports.summarizer import Summarizer

from .executor import Executor
from .guard import GuardReport, PlanGuard
from .resolver import Resolver
from .builder import SnapshotBuilder

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ReconcileMetrics
# ---------------------------------------------------------------------------


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
    pending_events: list = field(default_factory=list)

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

    @staticmethod
    def from_guard_reports(
        reports: list[GuardReport], ) -> tuple[int, dict[str, int]]:
        """Aggregate guard metrics from reports."""
        total = sum(r.total_rejects for r in reports)
        codes: dict[str, int] = {}
        for r in reports:
            for code, count in r.counts_by_code().items():
                codes[code] = codes.get(code, 0) + count
        return total, codes


# ---------------------------------------------------------------------------
# RebalancePhase
# ---------------------------------------------------------------------------


class RebalancePhase:
    """
    Structure rebalance and plan-level meta updates.

    Decoupled from Keeper - uses injected components instead of callbacks.
    """

    def __init__(
        self,
        *,
        strategy: Strategy,
        guard: PlanGuard,
        resolver: Resolver,
        executor: Executor,
        uow_factory: UoWFactory,
        snapshot_builder: SnapshotBuilder,
        terminal_policy: TerminalPolicy,
    ):
        self._strategy = strategy
        self._guard = guard
        self._resolver = resolver
        self._executor = executor
        self._uow_factory = uow_factory
        self._snapshot_builder = snapshot_builder
        self._terminal_policy = terminal_policy

    async def run(
        self,
        snapshot: Snapshot,
        uow: UnitOfWork,
        metrics: ReconcileMetrics,
    ) -> tuple[list[TreeEvent], bool, list[GuardReport]]:
        """
        Execute rebalance phase.

        Returns:
            (events, plan_renamed_nodes, guard_reports)
        """
        events: list[TreeEvent] = []
        guard_reports: list[GuardReport] = []
        plan_renamed_nodes = False

        zone = snapshot.zone
        depth = snapshot.target.path.value.count(".")
        is_terminal = self._terminal_policy.is_terminal(depth)
        allow_group = self._terminal_policy.allow_group(depth)

        # Skip rebalance for terminal categories (unless grouping allowed)
        if is_terminal and not allow_group:
            metrics.allow_rebalance = False
            return events, plan_renamed_nodes, guard_reports

        # Skip if healthy and no pending
        if zone == Zone.HEALTHY and not snapshot.has_pending:
            return events, plan_renamed_nodes, guard_reports

        metrics.rebalance_tried = True

        # Get plan from strategy
        raw_plan = await self._strategy.draft(snapshot)
        if raw_plan is None:
            return events, plan_renamed_nodes, guard_reports

        # Validate raw plan
        raw_plan, raw_report = self._guard.validate_raw_plan(raw_plan)
        guard_reports.append(raw_report)

        # Resolve to executable plan
        plan = self._resolver.compile(raw_plan, snapshot)

        # Validate resolved plan
        plan, resolved_report = self._guard.validate_plan(plan)
        guard_reports.append(resolved_report)

        if plan.is_empty():
            return events, plan_renamed_nodes, guard_reports

        # Execute plan
        exec_events = self._executor.execute(plan, snapshot, uow)
        events.extend(exec_events)
        metrics.rebalance_done = True

        # Apply plan-level category updates
        plan_renamed_nodes = self._apply_plan_category_updates(
            plan, snapshot, uow)

        return events, plan_renamed_nodes, guard_reports

    def _apply_plan_category_updates(
        self,
        plan: Plan,
        snapshot: Snapshot,
        uow: UnitOfWork,
    ) -> bool:
        """Apply plan-level updates to parent category."""
        target = snapshot.target
        renamed = False

        # Update summary if provided
        if plan.has_summary_update():
            meta = normalize_category_meta(
                build_category_meta(
                    raw_summary=plan.updated_summary,
                    keywords=tuple(plan.updated_keywords or []),
                ))
            updated = target.with_category_meta(meta)
            uow.register_dirty(updated)
            target = updated

        # Update name if provided and editable
        if plan.has_name_update() and target.name_editable:
            uow.register_rename(target.id, plan.updated_name)
            renamed = True

        return renamed


# ---------------------------------------------------------------------------
# RollupPhase
# ---------------------------------------------------------------------------


class RollupPhase:
    """
    Terminal rollup - archives old leaves and creates rollup summary.

    Decoupled from Keeper - uses injected components.
    """

    def __init__(
        self,
        *,
        uow_factory: UoWFactory,
        terminal_config: TerminalConfig,
        summarizer: Summarizer,
    ):
        self._uow_factory = uow_factory
        self._config = terminal_config
        self._summarizer = summarizer

    async def run(
        self,
        snapshot: Snapshot,
        uow: UnitOfWork,
        metrics: ReconcileMetrics,
    ) -> bool:
        """
        Execute rollup phase if conditions met.

        Returns:
            True if rollup was performed
        """
        depth = snapshot.target.path.value.count(".")
        if depth < self._config.terminal_depth:
            return False

        active_leaves = snapshot.leaves
        if len(active_leaves) < self._config.rollup_trigger_count:
            return False

        # Sort by ingestion time, oldest first
        sorted_leaves = sorted(
            active_leaves,
            key=lambda n: n.payload.get("_ingested_at", ""),
        )

        # Take oldest batch for rollup
        batch_size = max(
            self._config.min_rollup_batch,
            len(sorted_leaves) - self._config.rollup_trigger_count // 2,
        )
        batch = sorted_leaves[:batch_size]

        if len(batch) < self._config.min_rollup_batch:
            return False

        # Build rollup content
        rollup_content = await self._build_rollup_content(batch)

        # Create rollup leaf
        window_label = self._compute_window_label()
        rollup_name = f"rollup_{window_label}_{uuid4().hex[:6]}"

        rollup_node = Node.create_leaf(
            parent_id=snapshot.target.id,
            parent_path=snapshot.target.path.value,
            name=rollup_name,
            content=rollup_content,
            payload={
                "_rollup": True,
                "_window": window_label,
                "_source_count": len(batch),
                "_created_at": datetime.utcnow().isoformat(),
            },
            stage=NodeStage.ACTIVE,
        )
        uow.register_new(rollup_node)

        # Archive source leaves (mark as COLD)
        for leaf in batch:
            cold_leaf = leaf.with_stage(NodeStage.COLD)
            uow.register_dirty(cold_leaf)

        metrics.rolled_up = True
        return True

    async def _build_rollup_content(self, leaves: list[Node]) -> str:
        """Build rollup summary from leaves."""
        contents = [leaf.content for leaf in leaves if leaf.content]
        combined = "\n\n---\n\n".join(contents)

        # Use summarizer if available
        try:
            summary = await self._summarizer.summarize(combined)
            return summary
        except Exception:
            # Fallback to simple concatenation
            return f"[Rollup of {len(leaves)} items]\n\n{combined[:2000]}..."

    def _compute_window_label(self) -> str:
        """Compute window label based on config."""
        now = datetime.utcnow()
        if self._config.rollup_window == "weekly":
            return f"{now.year}-w{now.isocalendar()[1]:02d}"
        elif self._config.rollup_window == "monthly":
            return f"{now.year}-m{now.month:02d}"
        else:
            quarter = (now.month - 1) // 3 + 1
            return f"{now.year}-q{quarter}"


# ---------------------------------------------------------------------------
# PostRebalancePhases
# ---------------------------------------------------------------------------


class PostRebalancePhases:
    """
    Post-rebalance phases: lifecycle, summary, propagation.

    Decoupled from Keeper - uses injected components.
    """

    def __init__(
        self,
        *,
        store: NodeStore,
        summarizer: Summarizer,
        policy: Policy,
    ):
        self._store = store
        self._summarizer = summarizer
        self._policy = policy

    async def lifecycle_phase(
        self,
        snapshot: Snapshot,
        uow: UnitOfWork,
        metrics: ReconcileMetrics,
    ) -> list[Persisted]:
        """Promote pending nodes to active."""
        events: list[Persisted] = []

        for pending in snapshot.pending:
            promoted = pending.with_stage(NodeStage.ACTIVE)
            uow.register_dirty(promoted)
            events.append(
                Persisted(
                    leaf_id=pending.id,
                    parent_id=snapshot.target.id,
                    leaf_path=pending.path.value,
                    parent_path=snapshot.target.path.value,
                ))
            metrics.promoted += 1

        return events

    async def summary_phase(
        self,
        snapshot: Snapshot,
        uow: UnitOfWork,
        metrics: ReconcileMetrics,
    ) -> bool:
        """Update category summary based on children."""
        target = snapshot.target

        # Check if there's content to summarize
        has_content = (any(leaf.content for leaf in snapshot.leaves)
                       or any(pending.content for pending in snapshot.pending)
                       or any(sub.summary for sub in snapshot.subcategories))
        if not has_content:
            return False

        # Generate new summary using summarizer
        try:
            new_summary, new_keywords = await self._summarizer.summarize(
                snapshot)
        except Exception:
            return False

        if new_summary == target.summary:
            return False

        # Update category meta
        keywords = tuple(new_keywords) if new_keywords else tuple(
            target.category_meta.get("keywords", []))
        meta = normalize_category_meta(
            build_category_meta(
                raw_summary=new_summary,
                keywords=keywords,
            ))
        updated = target.with_category_meta(meta)
        uow.register_dirty(updated)
        metrics.summary_changed = True
        return True

    async def propagation_phase(
        self,
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
