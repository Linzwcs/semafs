"""HybridStrategy - LLM-powered reorganization."""

from __future__ import annotations
import logging

from ...core.capacity import Zone
from ...core.raw import RawPlan
from ...core.snapshot import Snapshot
from ...ports.strategy import Strategy
from .sanitize import parse_keywords, parse_raw_ops

logger = logging.getLogger(__name__)


class HybridStrategy(Strategy):
    """LLM-first strategy without rule fallback."""

    def __init__(self, adapter, force_threshold: int | None = None):
        self._adapter = adapter
        self._force_threshold = force_threshold

    async def draft(self, snapshot: Snapshot) -> RawPlan | None:
        """Create plan using hybrid decision logic."""
        zone = snapshot.zone

        # Healthy + no pending -> skip
        if zone == Zone.HEALTHY and not snapshot.has_pending:
            return None

        # Healthy with pending: lifecycle handling happens in Keeper.
        # No structural op needed by default.
        if zone == Zone.HEALTHY:
            return None

        # Pressured or overflow -> call LLM
        try:
            result = await self._adapter.call(snapshot)
            raw_ops = result.get("ops", [])
            parsed = parse_raw_ops(raw_ops, snapshot)
            return RawPlan(
                ops=tuple(parsed),
                updated_summary=result.get("updated_summary"),
                updated_keywords=parse_keywords(
                    result.get("updated_keywords", [])),
                updated_name=result.get("updated_name"),
                reasoning=result.get("overall_reasoning", ""),
            )

        except Exception as e:
            logger.warning("LLM call failed: %s, skip rebalance this round", e)
            return None
