"""HybridStrategy - LLM-powered reorganization with rule-based fallback."""

from __future__ import annotations
import logging
from typing import Optional

from ..core.capacity import Zone
from ..core.node import NodeType
from ..core.ops import PersistOp
from ..core.raw import RawPlan, RawMerge, RawGroup, RawMove
from ..core.snapshot import Snapshot
from .rule import RuleOnlyStrategy

logger = logging.getLogger(__name__)

_rule = RuleOnlyStrategy()


def _resolve_id(raw_id: str, snapshot: Snapshot) -> Optional[str]:
    """Resolve short ID to full UUID."""
    for node in snapshot.leaves + snapshot.pending + snapshot.subcategories:
        if node.id == raw_id or node.id[:8] == raw_id[:8]:
            return node.id
    return raw_id


def _parse_ops(raw_ops: list[dict], snapshot: Snapshot) -> list:
    """Parse raw LLM ops into RawMerge/RawGroup/RawMove."""
    ops = []
    for item in raw_ops:
        try:
            op_type = item["op_type"]
            raw_ids = item.get("ids", [])
            ids = tuple(_resolve_id(i, snapshot) for i in raw_ids)

            if op_type == "MERGE":
                if len(ids) < 2:
                    continue
                ops.append(RawMerge(
                    source_ids=ids,
                    new_content=item.get("content", ""),
                    new_name=item.get("name", ""),
                ))
            elif op_type == "GROUP":
                if len(ids) < 2:
                    continue
                ops.append(RawGroup(
                    source_ids=ids,
                    category_name=item.get("name", ""),
                    category_summary=item.get("content", ""),
                ))
            elif op_type == "MOVE":
                if not ids:
                    continue
                ops.append(RawMove(
                    leaf_id=ids[0],
                    target_name=item.get("path_to_move", ""),
                ))
        except (ValueError, KeyError, TypeError) as e:
            logger.warning("Failed to parse op: %s, skipping: %s", e, item)
    return ops


class HybridStrategy:
    """LLM-powered strategy with rule-based fallback."""

    def __init__(self, adapter, force_threshold: int | None = None):
        self._adapter = adapter
        self._force_threshold = force_threshold

    async def draft(self, snapshot: Snapshot) -> RawPlan | None:
        """Create plan using hybrid decision logic."""
        zone = snapshot.zone

        # Healthy + no pending → skip
        if zone == Zone.HEALTHY and not snapshot.has_pending:
            return None

        # Healthy with pending → rule fallback (no LLM cost)
        if zone == Zone.HEALTHY:
            return self.fallback(snapshot)

        # Pressured or overflow → call LLM
        try:
            result = await self._adapter.call(snapshot)
            raw_ops = result.get("ops", [])
            parsed = _parse_ops(raw_ops, snapshot)

            # Add PersistOps for pending nodes not covered by LLM ops
            covered_ids = set()
            for op in parsed:
                if isinstance(op, (RawMerge, RawGroup)):
                    covered_ids.update(op.source_ids)
                elif isinstance(op, RawMove):
                    covered_ids.add(op.leaf_id)

            persist_ops = []
            for p in snapshot.pending:
                if p.id not in covered_ids:
                    persist_ops.append(PersistOp(leaf_id=p.id))

            all_ops = persist_ops + parsed

            return RawPlan(
                ops=tuple(all_ops),
                updated_summary=result.get("updated_content"),
                updated_name=result.get("updated_name"),
                reasoning=result.get("overall_reasoning", ""),
            )

        except Exception as e:
            logger.warning("LLM call failed: %s, falling back to rules", e)
            return self.fallback(snapshot)

    def fallback(self, snapshot: Snapshot) -> RawPlan:
        """Delegate to RuleOnlyStrategy."""
        return _rule.fallback(snapshot)
