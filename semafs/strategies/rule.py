"""RuleOnlyStrategy - Deterministic reorganization without LLM."""

from __future__ import annotations
import math

from ..core.node import NodeType
from ..core.ops import PersistOp, GroupOp
from ..core.raw import RawPlan, RawGroup
from ..core.snapshot import Snapshot


class RuleOnlyStrategy:
    """
    Deterministic strategy that never calls an LLM.

    Algorithm:
        1. PersistOp for each pending fragment
        2. GroupOp batching when over budget
        3. Update parent summary by appending new content
    """

    async def draft(self, snapshot: Snapshot) -> RawPlan | None:
        """Always delegates to fallback."""
        return self.fallback(snapshot)

    def fallback(self, snapshot: Snapshot) -> RawPlan:
        """Create guaranteed rule-based plan."""
        ops = []
        total_after = snapshot.active_children + len(snapshot.pending)

        # Persist all pending fragments
        for node in snapshot.pending:
            ops.append(PersistOp(leaf_id=node.id))

        # Group if over budget
        if total_after > snapshot.budget.soft:
            leaf_nodes = [n for n in snapshot.leaves if n.node_type == NodeType.LEAF]
            target_per_group = max(2, snapshot.budget.soft // 2)
            num_groups = math.ceil(len(leaf_nodes) / target_per_group)

            if num_groups > 1 and len(leaf_nodes) >= 2:
                group_ops = []
                for i in range(num_groups):
                    start = i * target_per_group
                    end = min(start + target_per_group, len(leaf_nodes))
                    batch = leaf_nodes[start:end]

                    if len(batch) >= 2:
                        batch_ids = tuple(n.id for n in batch)
                        summary = "; ".join(
                            n.content[:50] for n in batch if n.content
                        )[:200]
                        group_ops.append(
                            RawGroup(
                                source_ids=batch_ids,
                                category_name=f"batch_{i + 1}",
                                category_summary=summary or f"Batch {i + 1}",
                            )
                        )
                ops.extend(group_ops)

        # Build updated summary
        parts = [n.content for n in snapshot.pending if n.content]
        new_append = "\n\n".join(parts)
        old_summary = snapshot.target.summary or ""

        if old_summary and new_append:
            updated = f"{old_summary}\n\n[New records]\n{new_append}"
        else:
            updated = old_summary or new_append

        return RawPlan(
            ops=tuple(ops),
            updated_summary=updated[:1500],
            reasoning="Rule strategy: deterministic reorganization",
        )
