"""
Hybrid strategy: LLM-powered reorganization with rule-based fallback.

This module provides HybridStrategy, which combines LLM intelligence
with deterministic fallback rules for robust reorganization.

Decision Logic:
    1. No pending + under threshold → None (skip maintenance)
    2. Pending + under threshold → Rule fallback (no LLM cost)
    3. Over threshold or force_llm → Call LLM for semantic analysis
    4. LLM failure → Rule fallback (guaranteed reliability)

The hybrid approach balances:
    - Cost efficiency: Only call LLM when necessary
    - Intelligence: Use LLM for complex semantic decisions
    - Reliability: Always have a fallback when LLM fails

Usage:
    adapter = OpenAIAdapter(client, model="gpt-4o")
    strategy = HybridStrategy(adapter, max_children=10)
    plan = await strategy.create_plan(context, max_children=10)
"""
from __future__ import annotations
import logging
from typing import Dict, List, Optional
from ..core.enums import OpType
from ..core.node import TreeNode
from ..core.ops import (AnyOp, GroupOp, MergeOp, MoveOp, PersistOp,
                        RebalancePlan, UpdateContext)
from ..ports.llm import BaseLLMAdapter
from ..ports.strategy import Strategy

logger = logging.getLogger(__name__)


def _resolve_id(raw_id: str, all_nodes: List[TreeNode]) -> Optional[str]:
    """
    Resolve a raw ID (possibly short) to full UUID.

    LLM may return 8-character short IDs from the prompt. This function
    attempts to match both full UUIDs and short prefixes.

    Args:
        raw_id: The ID string from LLM output.
        all_nodes: List of all nodes in context.

    Returns:
        The full UUID if matched, otherwise returns raw_id unchanged.
    """
    for n in all_nodes:
        if n.id == raw_id or n.id[:8] == raw_id[:8]:
            return n.id
    return raw_id


def _parse_ops(raw_ops: List[Dict], all_nodes: List[TreeNode]) -> List[AnyOp]:
    """
    Parse raw LLM operation dictionaries into typed Op objects.

    Handles LLM hallucinations gracefully by:
    - Skipping operations with invalid op_types
    - Skipping MERGE/GROUP with fewer than 2 IDs
    - Logging warnings for parsing failures

    Args:
        raw_ops: List of operation dicts from LLM response.
        all_nodes: List of all nodes for ID resolution.

    Returns:
        List of validated Op objects (MergeOp, GroupOp, MoveOp).
    """
    ops: List[AnyOp] = []

    for item in raw_ops:
        try:
            op_type = OpType(item["op_type"])
            raw_ids = item.get("ids", [])
            ids = tuple(_resolve_id(i, all_nodes) for i in raw_ids)
            reasoning = item.get("reasoning", "")

            match op_type:
                case OpType.MERGE:
                    if len(ids) < 2:
                        logger.warning("MERGE requires at least 2 IDs, skipping")
                        continue
                    ops.append(
                        MergeOp(
                            ids=ids,
                            content=item.get("content", ""),
                            name=item.get("name", ""),
                            reasoning=reasoning,
                        ))

                case OpType.GROUP:
                    if len(ids) < 2:
                        logger.warning("GROUP requires at least 2 IDs, skipping")
                        continue
                    ops.append(
                        GroupOp(
                            ids=ids,
                            name=item.get("name", ""),
                            content=item.get("content", ""),
                            reasoning=reasoning,
                        ))

                case OpType.MOVE:
                    ops.append(
                        MoveOp(
                            ids=(ids[0], ) if ids else (),
                            path_to_move=item.get("path_to_move", ""),
                            name=item.get("name", ""),
                            reasoning=reasoning,
                        ))

        except (ValueError, KeyError, TypeError) as e:
            logger.warning("Failed to parse Op: %s, skipping: %s", e, item)

    return ops


class HybridStrategy(Strategy):
    """
    Hybrid strategy combining LLM intelligence with rule-based fallback.

    HybridStrategy makes intelligent decisions about when to call the LLM:
    - Small directories: Use simple rules (no LLM cost)
    - Large directories: Use LLM for semantic reorganization
    - Failures: Gracefully fall back to rules

    The strategy respects the `_force_llm` flag in category payload,
    which triggers LLM-based "semantic rethink" regardless of size.

    Attributes:
        _adapter: The LLM adapter for making API calls.
        _max_children: Default threshold for triggering LLM.

    Example:
        adapter = OpenAIAdapter(client, "gpt-4o")
        strategy = HybridStrategy(adapter, max_children=10)

        plan = await strategy.create_plan(context, max_children=10)
        if plan:
            await executor.execute(plan, context, uow)
    """

    def __init__(
        self,
        adapter: BaseLLMAdapter,
        max_children: int = 10,
    ):
        """
        Initialize the hybrid strategy.

        Args:
            adapter: LLM adapter for making API calls.
            max_children: Default threshold (can be overridden at call-time).
        """
        self._adapter = adapter
        self._max_children = max_children

    async def create_plan(self, context: UpdateContext,
                          max_children: int) -> Optional[RebalancePlan]:
        """
        Create a reorganization plan using hybrid decision logic.

        Decision Flow:
            1. Check force_llm flag (triggers LLM regardless of size)
            2. If no pending + under threshold → return None
            3. If under threshold → use rule fallback
            4. Otherwise → call LLM, fallback on failure

        Args:
            context: Snapshot of the category's current state.
            max_children: Maximum children threshold for this call.

        Returns:
            RebalancePlan with operations, or None if no action needed.
        """
        # Use call-time argument if provided, else instance default
        effective_max = max_children if max_children is not None else self._max_children

        total_nodes = len(context.all_nodes)
        force_llm = context.parent.payload.get("_force_llm", False)

        # Decision logic without force_llm
        if not force_llm:
            # No pending fragments and under capacity → skip
            if not context.pending_nodes and total_nodes <= effective_max:
                return None

            # Under capacity → use simple rules
            if total_nodes <= effective_max:
                logger.info(
                    "Directory under capacity (%d/%d), using rule fallback",
                    total_nodes, effective_max)
                return self.create_fallback_plan(context, effective_max)

        # Force LLM triggered (e.g., after GROUP operation)
        if force_llm:
            logger.info(
                "Force LLM flag detected, performing deep semantic restructure for '%s'",
                context.parent.path)

        # Call LLM for semantic analysis
        try:
            result = await self._adapter.call(context,
                                              max_children=effective_max)
            raw_ops = result.get("ops", [])
            parsed_ops = _parse_ops(raw_ops, list(context.all_nodes))

        except Exception as e:
            logger.warning("LLM call or parsing failed: %s, falling back to rules", e)
            return self.create_fallback_plan(context, effective_max)

        # Build reasoning message
        reasoning = result.get("overall_reasoning", "")
        if not raw_ops:
            reasoning = reasoning or "LLM: Structure is healthy, no changes needed"
        elif not parsed_ops:
            reasoning = "LLM operations were invalid after validation, filtered to empty"

        return RebalancePlan(
            ops=tuple(parsed_ops),
            updated_content=result.get("updated_content", ""),
            updated_name=result.get("updated_name"),
            overall_reasoning=reasoning,
            should_dirty_parent=result.get("should_dirty_parent", False),
            is_llm_plan=True,
        )

    def create_fallback_plan(self, context: UpdateContext,
                             max_children: int) -> RebalancePlan:
        """
        Create a guaranteed fallback plan using simple rules.

        This method never calls LLM and never raises exceptions.
        It simply converts all PENDING_REVIEW fragments to ACTIVE leaves.

        Algorithm:
            1. Create PersistOp for each pending fragment
            2. Append fragment content to parent summary
            3. Truncate updated content to prevent bloat

        Args:
            context: Snapshot of the category's current state.
            max_children: Maximum children threshold (unused but required).

        Returns:
            RebalancePlan with PersistOps (never None).
        """
        ops = []

        # Create PersistOp for each pending fragment
        for node in context.pending_nodes:
            payload = dict(node.payload)
            ops.append(
                PersistOp(
                    ids=(node.id, ),
                    name=f"leaf_{node.id[:8]}",
                    content=node.content,
                    payload=payload,
                    reasoning="Rule strategy: directory under capacity, archive fragment directly",
                ))

        # Build updated parent content
        content_parts = [n.content for n in context.pending_nodes if n.content]
        new_append = "\n\n".join(content_parts)

        old_content = context.parent.content or ""
        if old_content and new_append:
            updated_content = f"{old_content}\n\n[New records]\n{new_append}"
        else:
            updated_content = old_content or new_append

        return RebalancePlan(
            ops=tuple(ops),
            updated_content=updated_content[:1500],  # Truncate to prevent bloat
            overall_reasoning="Rule strategy: smoothly absorb new fragments",
            is_llm_plan=False,
        )
