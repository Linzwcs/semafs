from __future__ import annotations
import logging
from typing import Dict, List, Optional
from ..core.enums import OpType
from ..core.node import TreeNode
from ..core.ops import (AnyOp, GroupOp, MergeOp, MoveOp, PersistOp,
                        RebalancePlan, UpdateContext)
from ..ports.llm import BaseLLMAdapter
from ..ports.strategy import LLMStrategy

logger = logging.getLogger(__name__)


def _resolve_id(raw_id: str, all_nodes: List[TreeNode]) -> Optional[str]:
    """将短 ID 解析为完整 node.id。"""
    for n in all_nodes:
        if n.id == raw_id or n.id[:8] == raw_id[:8]:
            return n.id
    return raw_id


def _parse_ops(raw_ops: List[Dict], all_nodes: List[TreeNode]) -> List[AnyOp]:

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
                        logger.warning("MERGE ids 不足 2 个，跳过")
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
                        logger.warning("GROUP ids 不足 2 个，跳过")
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
            logger.warning("解析 Op 失败: %s，跳过: %s", e, item)
    return ops


class HybridLLMStrategy(LLMStrategy):
    """
    混合策略：实现 LLMStrategy 端口。

    决策逻辑：
    1. 无 inbox 且在阈值内 → None（无需整理）
    2. 有 inbox 但总数少（< max_nodes）→ 规则策略（不调 LLM）
    3. 超阈值或有 inbox 且数量多 → 调 LLM
    4. LLM 失败 → fallback 规则策略
    """

    def __init__(
        self,
        adapter: BaseLLMAdapter,
        max_nodes: int = 10,
    ):
        self._adapter = adapter
        self._max_nodes = max_nodes

    async def create_plan(self, context: UpdateContext,
                          max_children: int) -> Optional[RebalancePlan]:
        # Use the argument passed in at call-time if provided, else fall back
        # to the instance default.  This lets SemaFS pass self._max_children
        # through the strategy call without the strategy needing to know about it.
        effective_max = max_children if max_children is not None else self._max_nodes

        total_nodes = len(context.all_nodes)
        force_llm = context.parent.payload.get("_force_llm", False)

        if not force_llm:
            if not context.pending_nodes and total_nodes <= effective_max:
                return None  # 无新碎片且未满，直接跳过

            if total_nodes <= effective_max:
                logger.info("目录未达上限 (%d/%d)，采用规则降级", total_nodes,
                            effective_max)
                return self.create_fallback_plan(context, effective_max)

        if force_llm:
            logger.info("检测到强制 LLM 指令，对 '%s' 进行深度语义重构", context.parent.path)

        try:
            result = await self._adapter.call(context, max_nodes=effective_max)
            raw_ops = result.get("ops", [])
            parsed_ops = _parse_ops(raw_ops, list(context.all_nodes))

        except Exception as e:
            logger.warning("LLM 调用或解析失败: %s，降级到规则策略", e)
            return self.create_fallback_plan(context, effective_max)

        reasoning = result.get("overall_reasoning", "")
        if not raw_ops:
            reasoning = reasoning or "LLM: 认为无需改变结构"
        elif not parsed_ops:
            reasoning = "LLM 的操作均不合法，过滤后为空"

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
        规则策略：将 PENDING 转为 ACTIVE (PersistOp)，并将内容追加到目录的 updated_content 中
        """
        ops = []
        for node in context.pending_nodes:
            payload = dict(node.payload)
            ops.append(
                PersistOp(
                    ids=(node.id, ),
                    name=f"leaf_{node.id[:8]}",
                    content=node.content,
                    payload=payload,
                    reasoning="规则策略：目录未满，直接归档碎片",
                ))

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
