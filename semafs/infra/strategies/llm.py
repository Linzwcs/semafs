from __future__ import annotations
import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from ...models.enums import NodeType, OpType
from ...models.ops import (
    AnyOp,
    MergeOp,
    MoveOp,
    NodeUpdateContext,
    NodeUpdateOp,
    SplitOp,
)
from ...models.nodes import TreeNode
from ...interface import NodeUpdateStrategy
from .rule import RuleBasedStrategy

logger = logging.getLogger(__name__)

# 打印 LLM 算子轨迹，便于调试「未能成功保存记忆」等问题
_DEBUG_OPS = os.environ.get("SEMAFS_DEBUG_OPS", "1") in ("1", "true", "yes")


def _print_llm_result(context_path: str, result: Dict[str, Any]) -> None:
    """打印 LLM 返回的原始 tree_ops 结果。"""
    if not _DEBUG_OPS:
        return
    raw_ops = result.get("ops", [])
    print(f"\n[LLM Ops] 目录 {context_path} 原始返回:")
    print(
        f"  overall_reasoning: {result.get('overall_reasoning', '')[:80]}...")
    print(f"  updated_content: {result.get('updated_content', '')[:60]}...")
    print(f"  ops 数量: {len(raw_ops)}")
    for i, op in enumerate(raw_ops):
        print(f"  op[{i}] {op.get('op_type')}: ids={op.get('ids')} "
              f"reasoning={op.get('reasoning', '')[:40]}...")
        if op.get("op_type") == "SPLIT":
            print(f"       name={op.get('name')}")
        if op.get("path_to_move"):
            print(
                f"       path_to_move={op['path_to_move']} name={op.get('name')}"
            )
        if op.get("content"):
            print(f"       content={op['content'][:50]}...")


def _print_parsed_ops(context_path: str, parsed_ops: List[AnyOp]) -> None:
    """打印解析后的算子列表。"""
    if not _DEBUG_OPS:
        return
    print(f"\n[LLM Ops] 目录 {context_path} 解析后:")
    for i, p in enumerate(parsed_ops):
        base = f"  parsed[{i}] {p.op_type.value} ids={list(p.ids)}"
        if p.op_type == OpType.SPLIT:
            print(f"{base} name={getattr(p, 'name', '')}")
        elif hasattr(p, "path_to_move") and p.path_to_move:
            print(
                f"{base} path_to_move={p.path_to_move} name={getattr(p, 'name', '')}"
            )
        elif hasattr(p, "content"):
            print(
                f"{base} name={getattr(p, 'name', '')} content={p.content[:40] if p.content else ''}..."
            )
        else:
            print(base)


_TREE_OPS_SCHEMA: Dict[str, Any] = {
    "name":
    "tree_ops",
    "description": ("决定如何整理目录中的记忆碎片。返回一组操作（merge/split/move）。"
                    "如果不需要改变结构，返回 ops=[]。"),
    "input_schema": {
        "type": "object",
        "required": ["ops", "overall_reasoning"],
        "properties": {
            "ops": {
                "type": "array",
                "description": "操作列表，可为空",
                "items": {
                    "type": "object",
                    "required": ["op_type", "ids", "reasoning"],
                    "properties": {
                        "op_type": {
                            "type": "string",
                            "enum": ["MERGE", "SPLIT", "MOVE"]
                        },
                        "ids": {
                            "type":
                            "array",
                            "items": {
                                "type": "string"
                            },
                            "description":
                            "MERGE: 至少 2 个叶子 ID；SPLIT: 至少 2 个叶子 ID（每个新 category 至少 2 条）；MOVE: 仅 1 个 ID"
                        },
                        "reasoning": {
                            "type": "string"
                        },
                        "name": {
                            "type":
                            "string",
                            "description":
                            "MERGE/MOVE 时新节点的语义化名称；SPLIT 时新 category 名称。"
                            "必须根据 ids 对应节点的 content 提炼生成，不得随意编造。"
                            "格式：1) 仅英文 2) 有语义 3) 简洁 4) 空格用下划线 _ 代替"
                        },
                        "content": {
                            "type":
                            "string",
                            "description":
                            "MERGE 的合并内容；SPLIT 时新 category 的摘要：必须由你根据 ids 对应子节点内容做语义浓缩，不得添加子节点没有的信息"
                        },
                        "path_to_move": {
                            "type":
                            "string",
                            "description":
                            "MOVE 专用。目标 category 的**完整路径**，如 root.personal.diet_health。"
                            "必须从下方「可用子分类」中精确复制，不能编造或缩写。"
                        },
                    },
                },
            },
            "overall_reasoning": {
                "type": "string",
                "description": "整体决策理由"
            },
            "updated_content": {
                "type": "string",
                "description": "父目录的新摘要：必须由你根据子节点内容做语义浓缩，不得添加子节点没有的信息"
            },
            "updated_name": {
                "type":
                "string",
                "description":
                "父目录的新展示名（可选）。必须根据子节点 content 提炼，格式：仅英文、有语义、简洁、空格用 _ 代替"
            },
        },
    },
}


class LLMAdapter(ABC):
    """向 LLM 发送请求并返回 tree_ops tool call 结果。"""

    @abstractmethod
    async def call_with_tools(self, system: str, user: str) -> Dict[str, Any]:
        """
        返回 tree_ops 的 input dict，即 {"ops": [...], "overall_reasoning": "...", ...}
        如果 LLM 没有调用 tool，抛出 ValueError。
        """
        ...


class OpenAIAdapter(LLMAdapter):

    def __init__(self, client: Any, model: str = "gpt-4o-mini") -> None:
        self._client = client
        self._model = model

    async def call_with_tools(self, system: str, user: str) -> Dict[str, Any]:
        # 转为 OpenAI function calling 格式
        tool = {
            "type": "function",
            "function": {
                "name": _TREE_OPS_SCHEMA["name"],
                "description": _TREE_OPS_SCHEMA["description"],
                "parameters": _TREE_OPS_SCHEMA["input_schema"],
            },
        }
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": system
                },
                {
                    "role": "user",
                    "content": user
                },
            ],
            tools=[tool],
            tool_choice={
                "type": "function",
                "function": {
                    "name": "tree_ops"
                }
            },
        )

        msg = resp.choices[0].message
        if not msg.tool_calls:
            raise ValueError("LLM did not call tree_ops tool")
        return json.loads(msg.tool_calls[0].function.arguments)


class MockLLMAdapter(LLMAdapter):
    """
    模拟 LLM 适配器，用于无 API 测试。
    根据 inbox 内容返回预定义的 MERGE 操作。
    """

    def __init__(self,
                 responses: Optional[List[Dict[str, Any]]] = None) -> None:
        """
        :param responses: 可选的预定义响应列表，按调用顺序使用。
                          若为 None 或耗尽，则使用默认合并逻辑。
        """
        self._responses = responses or []
        self._call_count = 0

    async def call_with_tools(self, system: str, user: str) -> Dict[str, Any]:
        if self._call_count < len(self._responses):
            result = self._responses[self._call_count].copy()
            self._call_count += 1
            return result

        # 默认：仅从「待整理碎片（inbox）」段落解析 ID，避免误合并 CATEGORY 节点
        import re
        inbox_match = re.search(r"待整理碎片（inbox）:\s*\n(.*?)(?=\n\n|\Z)", user,
                                re.DOTALL)
        block = inbox_match.group(1) if inbox_match else user
        ids = re.findall(
            r"\[([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}|[0-9a-f]{8})\]",
            block, re.I)
        contents = re.findall(r"\[[^\]]+\]\s*([^\n]+)", block)
        merged = "\n\n".join(contents[:5]) if contents else "(模拟合并内容)"
        return {
            "ops": [{
                "op_type": "MERGE",
                "ids": ids[:10] or ["unknown"],
                "reasoning": "MockLLM: 默认合并所有待整理碎片",
                "content": merged,
                "name": "merged_by_mock",
            }],
            "overall_reasoning":
            "MockLLM 模拟决策",
            "updated_content":
            merged[:200],
        }


class AnthropicAdapter(LLMAdapter):

    def __init__(self,
                 client: Any,
                 model: str = "claude-haiku-4-5-20251001") -> None:
        self._client = client
        self._model = model

    async def call_with_tools(self, system: str, user: str) -> Dict[str, Any]:
        resp = await self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=system,
            messages=[{
                "role": "user",
                "content": user
            }],
            tools=[_TREE_OPS_SCHEMA],
            tool_choice={
                "type": "tool",
                "name": "tree_ops"
            },
        )
        for block in resp.content:
            if block.type == "tool_use" and block.name == "tree_ops":
                return block.input
        raise ValueError("LLM did not call tree_ops tool")


def _build_prompt(
    context: NodeUpdateContext,
    max_leaf_nodes: int = 5,
    max_category_nodes: int | None = None,
) -> tuple[str, str]:
    max_cat = max_category_nodes if max_category_nodes is not None else max_leaf_nodes
    all_nodes = list(context.children or []) + list(context.inbox or [])
    leaf_count = sum(1 for n in all_nodes
                     if getattr(n, "node_type", None) == NodeType.LEAF)
    category_count = sum(1 for n in all_nodes
                         if getattr(n, "node_type", None) == NodeType.CATEGORY)
    over_leaf = leaf_count > max_leaf_nodes
    over_cat = category_count > max_cat

    system = (
        "你是一个知识库整理助手。你的任务是分析目录中的记忆碎片，"
        "决定如何合并（merge）、拆分（split）或移动（move）它们，使目录保持整洁。\n"
        "规则：\n"
        "1. **SPLIT 约束**：每个 SPLIT 必须包含至少 2 个叶子（ids 至少 2 个）。不能将单条拆成新分类。\n"
        "2. **子分类数受限**：每层直接子分类数 ≤ 限制。**子分类已满时禁止 SPLIT**，只能通过 MOVE 将叶子移入已有子分类，并更新 updated_content。category 不能 merge。\n"
        "3. **层级优先**：当叶子数超限且子分类未满时，**优先 SPLIT 建立子分类**。按语义分组，每组至少 2 个叶子，SPLIT 成新 category。\n"
        "4. **合并仅用于高度相似**：仅当 2–3 条碎片语义几乎相同时才 MERGE。\n"
        "5. MOVE：将叶子移入**已存在的**子分类。path_to_move 必须从下方「可用子分类」中精确复制，不能自编路径。\n"
        "6. 如果碎片已经很整洁且未超限，ops 返回空列表即可。\n"
        "7. MERGE/SPLIT 必须提供 name。MOVE 必须提供 path_to_move（从「可用子分类」精确复制完整路径）及 name。\n"
        "8. **name 生成约束**：name 必须根据 ids 对应节点的 content 提炼生成。格式：仅英文、有语义、简洁、空格用 _ 代替。\n"
        "9. **CATEGORY 摘要约束**：updated_content 和 SPLIT 的 content 必须是子节点内容的语义浓缩，不得添加子节点没有的信息。\n"
        f"10. **每层数量约束**：直接叶子数 ≤ {max_leaf_nodes}，直接子分类数 ≤ {max_cat}。子分类满时只能 MOVE 或 MERGE，不能 SPLIT。\n"
        "请用中文填写 reasoning。")

    def _fmt_nodes(nodes: list, label: str) -> str:
        if not nodes:
            return f"{label}: (空)\n"
        lines = [f"{label}:"]
        for n in nodes:
            t = getattr(n, "node_type", None)
            typ = t.value if t else "?"
            lines.append(
                f"  [{n.id[:8]}] {typ} path={n.path} | {n.content[:80]}")
        return "\n".join(lines) + "\n"

    # 显式列出可用子分类，供 MOVE 的 path_to_move 精确引用
    sub_cats = [
        n for n in (context.children or [])
        if getattr(n, "node_type", None) == NodeType.CATEGORY
    ]
    available_cats = "\n".join(f"  - {c.path}"
                               for c in sub_cats) if sub_cats else "  (无)"
    available_block = f"可用子分类（MOVE 时 path_to_move 必须从此精确复制）:\n{available_cats}\n"

    hints = []
    if over_leaf:
        hints.append(f"叶子数 {leaf_count} > {max_leaf_nodes}")
    if over_cat:
        hints.append(f"子分类数 {category_count} > {max_cat}")
    cat_full = category_count >= max_cat
    if hints:
        limit_hint = f"\n⚠️ **{'；'.join(hints)}**。"
        if cat_full:
            limit_hint += f" 子分类已满({category_count}/{max_cat})，禁止 SPLIT，只能 MOVE 或 MERGE。"
        limit_hint += f" 使每层叶子 ≤ {max_leaf_nodes}、子分类 ≤ {max_cat}。\n"
    elif cat_full:
        limit_hint = f"\n⚠️ 子分类已满({category_count}/{max_cat})，禁止 SPLIT，只能 MOVE 或 MERGE。\n"
    else:
        limit_hint = "\n"
    user = (
        f"目录路径: {context.parent.path}\n"
        f"目录摘要: {context.parent.content or '(无)'}\n"
        f"当前：叶子 {leaf_count}/{max_leaf_nodes}，子分类 {category_count}/{max_cat}{limit_hint}\n"
        f"{available_block}\n" +
        _fmt_nodes(context.children, "已整理节点（children）") +
        _fmt_nodes(context.inbox, "待整理碎片（inbox）") +
        "\n请调用 tree_ops 工具，给出整理方案。ids 可用完整或前 8 位。")
    return system, user


def _resolve_ids(
    raw_ids: List[str],
    all_nodes: List["TreeNode"],
) -> tuple:
    """将 LLM 返回的短 ID (如 id[:8]) 解析为完整 node.id。"""
    id_map = {n.id: n.id for n in all_nodes}
    id_map.update({n.id[:8]: n.id for n in all_nodes})
    return tuple(id_map.get(i, i) for i in raw_ids)


def _parse_ops(
    raw_ops: List[Dict[str, Any]],
    all_nodes: Optional[List["TreeNode"]] = None,
) -> List[AnyOp]:
    all_nodes = all_nodes or []
    ops: List[AnyOp] = []
    for item in raw_ops:
        op_type = OpType(item["op_type"])
        raw_ids = item.get("ids", [])
        ids = _resolve_ids(raw_ids, all_nodes)
        reasoning = item.get("reasoning", "")
        if op_type == OpType.MERGE:
            ops.append(
                MergeOp(ids=ids,
                        reasoning=reasoning,
                        content=item.get("content", ""),
                        name=item.get("name")))
        elif op_type == OpType.SPLIT:
            ops.append(
                SplitOp(ids=ids,
                        reasoning=reasoning,
                        name=item.get("name") or "",
                        content=item.get("content", "")))
        elif op_type == OpType.MOVE:
            # MOVE 一次仅移动一个节点，多余 id 忽略
            ops.append(
                MoveOp(ids=ids[:1] if ids else (),
                       reasoning=reasoning,
                       path_to_move=item.get("path_to_move", ""),
                       name=item.get("name")))
    return ops


class LLMStrategy(NodeUpdateStrategy):
    """
    混合策略：
    - 数量少（< threshold）→ 跳过 LLM，使用规则摘要
    - 数量多 → 调用 LLM Tool Call
    - LLM 失败 → fallback 到规则合并
    """

    def __init__(
        self,
        adapter: LLMAdapter,
        max_leaf_nodes: int = 3,
        max_category_nodes: int | None = None,
    ) -> None:

        self._adapter = adapter
        self._max_category_nodes = max_category_nodes or max_leaf_nodes
        self._rule = RuleBasedStrategy(max_leaf_nodes)
        self._max_leaf_nodes = max_leaf_nodes

    async def create_update_op(
        self,
        context: NodeUpdateContext,
    ) -> Optional[NodeUpdateOp]:

        total = len(context.pending_nodes) + len(context.active_nodes)
        all_n = list(context.pending_nodes or []) + list(context.active_nodes
                                                         or [])
        leaf_count = sum(1 for n in all_n
                         if getattr(n, "node_type", None) == NodeType.LEAF)
        category_count = sum(
            1 for n in all_n
            if getattr(n, "node_type", None) == NodeType.CATEGORY)
        within_limits = (leaf_count <= self._max_leaf_nodes
                         and category_count <= self._max_category_nodes)
        if not context.pending_nodes and within_limits:
            return None

        if total < self._max_leaf_nodes and context.pending_nodes:
            return await self._rule.create_update_op(context)

        # 有 inbox 或 leaf/category 超限：调用 LLM

        system, user = _build_prompt(context, self._max_leaf_nodes,
                                     self._max_category_nodes)
        try:
            result = await self._adapter.call_with_tools(system, user)
        except Exception as e:
            logger.warning(f"LLM tool call 失败: {e}，降级到规则策略")
            return self.create_fallback_op(context)

        raw_ops = result.get("ops", [])
        _print_llm_result(context.parent.path, result)
        if not raw_ops:
            if _DEBUG_OPS:
                print(
                    f"[LLM Ops] 目录 {context.parent.path}: ops 为空，跳过整理（可能 LLM 认为无需改动）"
                )
            return None
        all_nodes = list(context.pending_nodes) + list(context.active_nodes)
        try:
            parsed_ops = _parse_ops(raw_ops, all_nodes)
        except Exception as e:
            logger.warning(f"解析 LLM ops 失败: {e}，降级到规则策略")
            return self.create_fallback_op(context)

        # 子分类已满时过滤掉 SPLIT；SPLIT 至少 2 个叶子（executor 会二次校验）
        if category_count >= self._max_category_nodes:
            parsed_ops = [o for o in parsed_ops if o.op_type != OpType.SPLIT]
        parsed_ops = [
            o for o in parsed_ops
            if o.op_type != OpType.SPLIT or len(o.ids) >= 2
        ]
        if not parsed_ops:
            return None

        _print_parsed_ops(context.parent.path, parsed_ops)
        return NodeUpdateOp(
            ops=parsed_ops,
            updated_content=result.get("updated_content", ""),
            updated_name=result.get("updated_name"),
            is_macro_change=True,
            overall_reasoning=result.get("overall_reasoning", "LLM 决策"),
        )

    def create_fallback_op(self, context: NodeUpdateContext) -> NodeUpdateOp:
        return self._rule.create_fallback_op(context)
