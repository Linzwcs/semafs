"""
Rule-only strategy: Deterministic reorganization without LLM.

This module provides RuleOnlyStrategy, which implements simple rule-based
reorganization. It never calls an LLM, making it suitable for:
- Testing and development
- Mock/demo modes
- Fallback when LLM is unavailable

Behavior:
    - Converts all PENDING_REVIEW fragments to ACTIVE leaves (PersistOp)
    - When node count exceeds max_children, creates GroupOps to batch nodes
    - Appends new content to the parent category summary
    - Never merges nodes semantically (no content consolidation)

Usage:
    strategy = RuleOnlyStrategy()
    plan = await strategy.create_plan(context, max_children=10)
    # Returns RebalancePlan with PersistOp/GroupOp for each pending fragment
"""
from __future__ import annotations
import math
from typing import List

from ..core.ops import PersistOp, GroupOp, RebalancePlan, UpdateContext, AnyOp
from ..ports.strategy import Strategy


class RuleOnlyStrategy(Strategy):
    """
    Deterministic strategy that never calls an LLM.

    RuleOnlyStrategy provides a simple, fast, and predictable way to
    process pending fragments. It's the guaranteed fallback used by
    HybridStrategy when LLM calls fail.

    The algorithm:
        1. For each PENDING_REVIEW fragment, create a PersistOp
        2. If total nodes exceed max_children, create GroupOps to batch
        3. Update parent content by appending new fragment summaries
        4. Return plan (always returns a plan, never None)

    This strategy is intentionally simple - no semantic understanding,
    no merging. It uses simple batching for grouping when needed.

    Example:
        strategy = RuleOnlyStrategy()
        plan = await strategy.create_plan(context, max_children=10)
        await executor.execute(plan, context, uow)
    """

    async def create_plan(self, context: UpdateContext,
                          max_children: int) -> RebalancePlan:
        """
        Create a rule-based reorganization plan.

        Always delegates to create_fallback_plan since this strategy
        doesn't use LLM at all.

        Args:
            context: Snapshot of the category's current state.
            max_children: Maximum children threshold for triggering grouping.

        Returns:
            RebalancePlan with PersistOps/GroupOps for all pending fragments.
        """
        return self.create_fallback_plan(context, max_children)

    def create_fallback_plan(self, context: UpdateContext,
                             max_children: int) -> RebalancePlan:
        """
        Create a guaranteed fallback plan.

        This method never returns None and never raises exceptions,
        making it safe to use when LLM calls fail.

        Algorithm:
            1. Calculate total nodes after persisting pending fragments
            2. If under max_children: create PersistOp for each pending
            3. If over max_children: create GroupOps to batch nodes
            4. Append fragment content to parent summary

        Args:
            context: Snapshot of the category's current state.
            max_children: Maximum children threshold.

        Returns:
            RebalancePlan with PersistOps/GroupOps for all pending fragments.
        """
        ops: List[AnyOp] = []

        total_after_persist = len(context.active_nodes) + len(context.pending_nodes)

        # If under capacity, just persist all pending fragments
        if total_after_persist <= max_children:
            for node in context.pending_nodes:
                ops.append(
                    PersistOp(
                        ids=(node.id, ),
                        name=f"leaf_{node.id[:8]}",
                        content=node.content,
                        payload=dict(node.payload),
                        reasoning="Rule strategy: archive inbox fragment",
                    ))
        else:
            # Over capacity: need to group nodes
            # First, persist pending fragments (they need to exist before grouping)
            for node in context.pending_nodes:
                ops.append(
                    PersistOp(
                        ids=(node.id, ),
                        name=f"leaf_{node.id[:8]}",
                        content=node.content,
                        payload=dict(node.payload),
                        reasoning="Rule strategy: persist before grouping",
                    ))

            # Now create GroupOps to batch existing leaves
            # We group the LEAF nodes (not categories) into batches
            from ..core.enums import NodeType
            leaf_nodes = [n for n in context.active_nodes
                          if n.node_type == NodeType.LEAF]

            # Calculate how many groups we need
            # Target: each group should have ~max_children/2 nodes
            # to leave room for future growth
            target_per_group = max(2, max_children // 2)
            num_groups = math.ceil(len(leaf_nodes) / target_per_group)

            if num_groups > 1 and len(leaf_nodes) >= 2:
                # Distribute leaves evenly across groups
                for i in range(num_groups):
                    start_idx = i * target_per_group
                    end_idx = min(start_idx + target_per_group, len(leaf_nodes))
                    batch = leaf_nodes[start_idx:end_idx]

                    if len(batch) >= 2:  # GroupOp requires at least 2 nodes
                        batch_ids = tuple(n.id for n in batch)
                        # Create a simple summary from batch contents
                        batch_summary = "; ".join(
                            n.content[:50] for n in batch if n.content
                        )[:200]

                        ops.append(
                            GroupOp(
                                ids=batch_ids,
                                name=f"batch_{i + 1}",
                                content=batch_summary or f"Batch {i + 1} of related items",
                                reasoning=f"Rule strategy: auto-grouping batch {i + 1} to reduce node count",
                            ))

        # Build updated parent content
        content_parts = [n.content for n in context.pending_nodes if n.content]
        new_append = "\n\n".join(content_parts)
        old_content = context.parent.content or ""

        if old_content and new_append:
            updated_content = f"{old_content}\n\n[New records]\n{new_append}"
        else:
            updated_content = old_content or new_append

        # Determine reasoning based on what operations we created
        has_groups = any(isinstance(op, GroupOp) for op in ops)
        if has_groups:
            reasoning = f"Rule strategy: auto-grouped nodes to stay under {max_children} limit"
        else:
            reasoning = "Rule strategy: smoothly absorb new fragments"

        return RebalancePlan(
            ops=tuple(ops),
            updated_content=updated_content[:1500],  # Truncate to prevent bloat
            overall_reasoning=reasoning,
            is_llm_plan=False,
        )
