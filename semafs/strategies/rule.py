"""
纯规则策略：不调用 LLM，始终使用 fallback 规则整理。

用于 Mock 模式、测试数据构建等无需 API 的场景。
"""
from __future__ import annotations

from ..core.ops import PersistOp, RebalancePlan, UpdateContext
from ..ports.strategy import LLMStrategy


class RuleOnlyStrategy(LLMStrategy):
    """始终返回规则策略（PersistOp）的整理计划，不调用 LLM。"""

    async def create_plan(
        self, context: UpdateContext, max_children: int
    ) -> RebalancePlan:
        return self.create_fallback_plan(context, max_children)

    def create_fallback_plan(
        self, context: UpdateContext, max_children: int
    ) -> RebalancePlan:
        ops = []
        for node in context.pending_nodes:
            ops.append(
                PersistOp(
                    ids=(node.id,),
                    name=f"leaf_{node.id[:8]}",
                    content=node.content,
                    payload=dict(node.payload),
                    reasoning="规则策略：直接归档碎片",
                )
            )
        content_parts = [n.content for n in context.pending_nodes if n.content]
        new_append = "\n\n".join(content_parts)
        old_content = context.parent.content or ""
        if old_content and new_append:
            updated_content = f"{old_content}\n\n[新增记录]\n{new_append}"
        else:
            updated_content = old_content or new_append
        return RebalancePlan(
            ops=tuple(ops),
            updated_content=updated_content[:1500],
            overall_reasoning="规则策略：平滑吸纳新碎片",
            is_llm_plan=False,
        )
