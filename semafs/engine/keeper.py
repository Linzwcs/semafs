"""Keeper - Thin maintenance orchestrator."""

import asyncio
import logging
from typing import Optional

from ..core.node import Node, NodeStage, NodeType
from ..core.capacity import Budget, Zone
from ..core.terminal import TerminalConfig, TerminalPolicy
from ..core.events import TreeEvent, Persisted
from ..core.snapshot import Snapshot
from ..ports.store import NodeStore
from ..ports.factory import UoWFactory
from ..ports.strategy import Strategy
from ..ports.bus import Bus
from ..ports.reviewer import PlanReviewer
from ..ports.summarizer import Summarizer
from ..ports.propagation import Policy, Signal
from .executor import Executor
from .compiler import DefaultPlanCompiler
from .validator import PlanValidator
from .phases import (
    PostRebalancePhases,
    RebalancePhase,
    ReconcileMetrics,
    RollupPhase,
)
from .resolver import Resolver
from .builder import SnapshotBuilder

logger = logging.getLogger(__name__)


class Keeper:
    """
    Thin maintenance orchestrator.

    Responsibilities (v2.1.15):
    1. Lock management (per-node concurrency control)
    2. Phase pipeline coordination
    3. Metrics aggregation and logging

    All business logic delegated to Phase components.
    """

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
        plan_reviewer: PlanReviewer | None = None,
    ):
        self._store = store
        self._uow_factory = uow_factory
        self._bus = bus
        self._default_budget = default_budget
        self._terminal_config = terminal_config
        self._locks: dict[str, asyncio.Lock] = {}

        # Build independent components
        validator = PlanValidator()
        terminal_policy = TerminalPolicy(config=terminal_config)
        snapshot_builder = SnapshotBuilder(budget=default_budget)

        # Initialize phases with injected dependencies
        self._snapshot_builder = snapshot_builder
        compiler = DefaultPlanCompiler(
            planner=strategy,
            resolver=resolver,
            validator=validator,
            reviewer=plan_reviewer,
        )
        self._rebalance_phase = RebalancePhase(
            compiler=compiler,
            executor=executor,
            uow_factory=uow_factory,
            snapshot_builder=snapshot_builder,
            terminal_policy=terminal_policy,
        )
        self._rollup_phase = RollupPhase(
            uow_factory=uow_factory,
            terminal_config=terminal_config,
            summarizer=summarizer,
        )
        self._post_phases = PostRebalancePhases(
            store=store,
            summarizer=summarizer,
            policy=policy,
        )

    async def reconcile(
        self,
        node_id: str,
        signal: Signal,
        cause: TreeEvent | None = None,
    ) -> ReconcileMetrics | None:
        """
        Reconcile a single category node.

        Pipeline:
        1. Acquire lock
        2. Build snapshot (transaction-aware)
        3. Run rebalance phase
        4. Run rollup phase (terminal only)
        5. Run post-rebalance phases (lifecycle, summary, propagation)
        6. Commit and publish events
        7. Propagate to parent if needed
        """
        lock = self._locks.setdefault(node_id, asyncio.Lock())

        async with lock:
            outcome = await self._reconcile_locked(node_id, signal, cause)
        if outcome is None:
            return None

        result, next_id, next_signal = outcome

        # Publish events AFTER lock is released to avoid deadlock
        if result and result.pending_events:
            for event in result.pending_events:
                await self._bus.publish(event)

        # Run upward propagation AFTER lock release and event publish.
        # Otherwise nested reconcile may publish an event that circles back
        # to this locked node and deadlock on lock acquisition.
        if next_id and next_signal:
            await self.reconcile(next_id, next_signal, cause)

        return result

    async def _reconcile_locked(
        self,
        node_id: str,
        signal: Signal,
        cause: TreeEvent | None,
    ) -> tuple[ReconcileMetrics, str | None, Signal | None] | None:
        """Execute reconcile pipeline under lock."""
        async with self._uow_factory.begin() as uow:
            # Build snapshot using transaction reader
            snapshot = await self._snapshot_builder.build(uow.reader, node_id)
            if snapshot is None:
                return None

            # Initialize metrics
            metrics = ReconcileMetrics(
                node_id=node_id,
                path=snapshot.target.path.value,
                zone=snapshot.zone.value,
                allow_rebalance=True,
                has_pending=snapshot.has_pending,
            )

            # Phase 1: Rebalance
            events, plan_renamed, issues = await self._rebalance_phase.run(
                snapshot, uow, metrics)

            # Update validation metrics
            rejects, codes = ReconcileMetrics.from_issues(issues)
            metrics.validation_rejects = rejects
            metrics.validation_codes = codes

            # Phase 2: Rollup (terminal categories only)
            await self._rollup_phase.run(snapshot, uow, metrics)

            # Phase 3: Post-rebalance (lifecycle, summary)
            # Note: lifecycle_events are NOT published to avoid recursive reconcile
            _ = await self._post_phases.lifecycle_phase(snapshot, uow, metrics)
            summary_changed = await self._post_phases.summary_phase(
                snapshot, uow, metrics)

            # Commit transaction
            await uow.commit()

        # Store events for publishing after lock release
        metrics.pending_events = events
        metrics.events = len(events)

        # Phase 4: Propagation decision.
        # Actual reconcile of parent is executed by caller after lock release.
        next_id, next_signal = await self._post_phases.propagation_phase(
            snapshot, signal, cause, summary_changed, plan_renamed)
        if next_id and next_signal:
            metrics.propagated = True

        self._log_metrics(metrics)
        return metrics, next_id, next_signal

    def _log_metrics(self, metrics: ReconcileMetrics) -> None:
        """Log reconcile metrics."""
        logger.info(
            "reconcile complete: path=%s zone=%s rebalance=%s promoted=%d "
            "rolled_up=%s summary=%s propagated=%s events=%d",
            metrics.path,
            metrics.zone,
            metrics.rebalance_done,
            metrics.promoted,
            metrics.rolled_up,
            metrics.summary_changed,
            metrics.propagated,
            metrics.events,
        )
        if metrics.validation_rejects > 0:
            logger.warning(
                "validation rejects: total=%d codes=%s",
                metrics.validation_rejects,
                metrics.validation_codes,
            )

    async def sweep(self, limit: int | None = None) -> int:
        """
        Sweep all overloaded categories.

        Returns number of categories processed.
        """
        overloaded = await self._find_overloaded(limit=limit)
        if not overloaded:
            return 0

        for node_id in overloaded:
            path = await self._store.canonical_path(node_id)
            signal = Signal(
                value=1.0,
                origin=path or "unknown",
                event_type="sweep",
            )
            await self.reconcile(node_id, signal)

        return len(overloaded)

    async def _find_overloaded(
        self,
        limit: int | None = None,
    ) -> tuple[str, ...]:
        """Find categories exceeding budget threshold."""
        all_ids = list(await self._store.all_node_ids())
        if not all_ids:
            return ()

        # Fetch paths and sort by depth (deepest first)
        paths = await asyncio.gather(
            *[self._store.canonical_path(nid) for nid in all_ids])
        ordered_ids = [
            nid for nid, _ in sorted(
                zip(all_ids, paths, strict=False),
                key=lambda item: (item[1] or "").count("."),
                reverse=True,
            )
        ]

        # Filter to categories only
        nodes = await asyncio.gather(
            *[self._store.get_by_id(nid) for nid in ordered_ids])
        category_ids = [
            nid for nid, node in zip(ordered_ids, nodes, strict=False)
            if node and node.node_type == NodeType.CATEGORY
        ]
        if not category_ids:
            return ()

        # Find overloaded
        children_list = await asyncio.gather(
            *[self._store.list_children(nid) for nid in category_ids])
        overloaded: list[str] = []
        for nid, children in zip(category_ids, children_list, strict=False):
            if self._default_budget.is_overflow(len(children)):
                overloaded.append(nid)
                if limit is not None and len(overloaded) >= limit:
                    break

        return tuple(overloaded)
