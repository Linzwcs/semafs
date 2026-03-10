"""
Rule-only strategy: Deterministic reorganization without LLM.

This module provides RuleOnlyStrategy, which implements simple rule-based
reorganization. It never calls an LLM, making it suitable for:
- Testing and development
- Mock/demo modes
- Fallback when LLM is unavailable

Behavior:
    - Converts all PENDING_REVIEW fragments to ACTIVE leaves (PersistOp)
    - Appends new content to the parent category summary
    - Never merges, groups, or moves nodes semantically

Usage:
    strategy = RuleOnlyStrategy()
    plan = await strategy.create_plan(context, max_children=10)
    # Returns RebalancePlan with PersistOp for each pending fragment
"""
from __future__ import annotations

from ..core.ops import PersistOp, RebalancePlan, UpdateContext
from ..ports.strategy import Strategy


class RuleOnlyStrategy(Strategy):
    """
    Deterministic strategy that never calls an LLM.

    RuleOnlyStrategy provides a simple, fast, and predictable way to
    process pending fragments. It's the guaranteed fallback used by
    HybridStrategy when LLM calls fail.

    The algorithm:
        1. For each PENDING_REVIEW fragment, create a PersistOp
        2. Update parent content by appending new fragment summaries
        3. Return plan (always returns a plan, never None)

    This strategy is intentionally simple - no semantic understanding,
    no merging, no grouping. It just persists fragments and moves on.

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
            max_children: Maximum children threshold (ignored by this strategy).

        Returns:
            RebalancePlan with PersistOps for all pending fragments.
        """
        return self.create_fallback_plan(context, max_children)

    def create_fallback_plan(self, context: UpdateContext,
                             max_children: int) -> RebalancePlan:
        """
        Create a guaranteed fallback plan.

        This method never returns None and never raises exceptions,
        making it safe to use when LLM calls fail.

        Algorithm:
            1. Create PersistOp for each pending fragment
            2. Append fragment content to parent summary
            3. Truncate updated content to 1500 chars

        Args:
            context: Snapshot of the category's current state.
            max_children: Maximum children threshold (ignored).

        Returns:
            RebalancePlan with PersistOps for all pending fragments.
        """
        ops = []

        # Create PersistOp for each pending fragment
        for node in context.pending_nodes:
            ops.append(
                PersistOp(
                    ids=(node.id, ),
                    name=f"leaf_{node.id[:8]}",
                    content=node.content,
                    payload=dict(node.payload),
                    reasoning="Rule strategy: archive inbox fragment",
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
