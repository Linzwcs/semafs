from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, Tuple
from ..core.ops import UpdateContext
from ..core.exceptions import LLMAdapterError
from ..core.enums import NodeType

# ── Tool Schema（Anthropic 格式，OpenAI 适配器会转换）──────────

_TREE_OPS_SCHEMA = {
    "name":
    "tree_ops",
    "description": ("决定如何整理目录中的记忆碎片。返回一组操作（merge/split/move）。"
                    "如果不需要改变结构，返回 ops=[]。"),
    "input_schema": {
        "type": "object",
        "required": ["ops", "overall_reasoning", "updated_content"],
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
                            "type": "array",
                            "items": {
                                "type": "string"
                            },
                            "description":
                            "MERGE≥2个叶子ID；SPLIT≥2个叶子ID；MOVE恰好1个ID",
                        },
                        "reasoning": {
                            "type": "string"
                        },
                        "name": {
                            "type":
                            "string",
                            "description":
                            ("节点名称。格式：仅英文、有语义、简洁、空格用下划线代替。"
                             "必须根据 ids 对应节点的 content 提炼，不得随意编造。"),
                        },
                        "content": {
                            "type":
                            "string",
                            "description":
                            "MERGE 的合并内容；SPLIT 新 CATEGORY 的摘要（语义浓缩，不添加原文没有的信息）",
                        },
                        "path_to_move": {
                            "type":
                            "string",
                            "description": ("MOVE 专用：目标 CATEGORY 的完整路径，"
                                            "必须从「可用子分类」列表中精确复制，不能编造。"),
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
                "description": "父目录的新摘要：必须根据子节点内容语义浓缩，不得添加子节点没有的信息",
            },
            "updated_name": {
                "type": "string",
                "description": "父目录的新展示名（可选）。格式：仅英文、有语义、简洁、下划线分隔",
            },
        },
    },
}
_TREE_OPS_SCHEMA["input_schema"]["properties"]["should_dirty_parent"] = {
    "type":
    "boolean",
    "description":
    "如果当前目录的摘要(updated_content)发生了重大语义变化或信息量激增，请设为 true，以通知父目录更新其描述。"
}
# ── Prompt 构建 ────────────────────────────────────────────────


def _build_prompt(
    context: UpdateContext,
    max_leaf: int,
    max_cat: int,
) -> Tuple[str, str]:
    """构建 system + user prompt，供所有适配器复用。"""
    all_nodes = context.all_nodes
    leaf_count = sum(1 for n in all_nodes if n.node_type == NodeType.LEAF)
    cat_count = sum(1 for n in all_nodes if n.node_type == NodeType.CATEGORY)
    cat_full = cat_count >= max_cat

    system = ("你是一个知识库整理助手。分析目录中的记忆碎片，"
              "决定如何合并（MERGE）、拆分（SPLIT）或移动（MOVE）它们。\n"
              "规则：\n"
              "1. MERGE：至少 2 个语义高度相似的叶子才合并。content 是语义浓缩，不是简单拼接。\n"
              "2. SPLIT：叶子数超限且子分类未满时，优先 SPLIT 建立子分类。每组至少 2 个叶子。\n"
              "3. MOVE：将叶子移入已存在的子分类。path_to_move 必须从「可用子分类」精确复制。\n"
              "4. 子分类已满时禁止 SPLIT，只能 MOVE 或 MERGE。\n"
              "5. CATEGORY 节点不参与 MERGE/MOVE/SPLIT。\n"
              "6. 已经整洁且未超限：ops 返回空列表。\n"
              "7. name 必须根据 ids 对应的内容提炼，格式：仅英文、有语义、简洁、下划线分隔。\n"
              "8. updated_content 必须是子节点内容的语义浓缩，不得添加没有的信息。\n"
              f"9. 每层约束：直接叶子数 ≤ {max_leaf}，子分类数 ≤ {max_cat}。\n"
              "请用中文填写 reasoning。")

    def _fmt(nodes: list, label: str) -> str:
        if not nodes:
            return f"{label}: (空)\n"
        lines = [f"{label}:"]
        for n in nodes:
            t = n.node_type.value if hasattr(n.node_type, "value") else "?"
            lines.append(f"  [{n.id[:8]}] {t} | {n.content[:80]}")
        return "\n".join(lines) + "\n"

    sub_cats = [
        n for n in (context.active_nodes) if n.node_type == NodeType.CATEGORY
    ]
    available = "\n".join(f"  - {c.path}" for c in sub_cats) or "  (无)"

    hints = []
    if leaf_count > max_leaf:
        hints.append(f"叶子数 {leaf_count} > {max_leaf}")
    if cat_count > max_cat:
        hints.append(f"子分类数 {cat_count} > {max_cat}")
    limit_hint = f"\n⚠️ {'；'.join(hints)}。" if hints else "\n"
    if cat_full:
        limit_hint += f" 子分类已满({cat_count}/{max_cat})，禁止 SPLIT。"
    limit_hint += "\n" if limit_hint != "\n" else ""

    user = (
        f"目录路径: {context.parent.path}\n"
        f"目录摘要: {context.parent.content or '(无)'}\n"
        f"当前：叶子 {leaf_count}/{max_leaf}，子分类 {cat_count}/{max_cat}{limit_hint}\n"
        f"可用子分类（MOVE 时 path_to_move 必须从此精确复制）:\n{available}\n\n" +
        _fmt(list(context.active_nodes), "已整理节点") +
        _fmt(list(context.pending_nodes), "待整理碎片（inbox）") +
        "\n请调用 tree_ops 工具，给出整理方案。ids 可用完整或前 8 位。")
    return system, user


class BaseLLMAdapter(ABC):
    """所有 LLM 适配器的基类，封装 prompt 构建和结果解析。"""

    @abstractmethod
    async def _call_api(self, system: str, user: str) -> Dict:
        """调用具体 LLM API，返回 tree_ops 的 input dict。"""
        ...

    async def call(self, context: UpdateContext, max_leaf: int,
                   max_cat: int) -> Dict:
        system, user = _build_prompt(context, max_leaf, max_cat)
        try:
            return await self._call_api(system, user)
        except Exception as e:
            raise LLMAdapterError(f"LLM API 调用失败: {e}") from e
