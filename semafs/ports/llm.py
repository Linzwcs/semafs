from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, Tuple
from ..core.ops import UpdateContext
from ..core.exceptions import LLMAdapterError
from ..core.enums import NodeType

# ── Tool Schema（Anthropic 格式，OpenAI 适配器会转换）──────────
_TREE_OPS_SCHEMA = {
    "name": "tree_ops",
    "description": "决定如何整理目录中的记忆碎片。通过执行 merge/group/move 维持目录整洁。",
    "input_schema": {
        "type":
        "object",
        "required":
        ["ops", "overall_reasoning", "updated_content", "should_dirty_parent"],
        "properties": {
            "ops": {
                "type": "array",
                "description": "操作列表。如果无需改变目录结构（未满载且无需聚类），返回空数组 []",
                "items": {
                    "type": "object",
                    "required": ["op_type", "ids", "reasoning", "name"],
                    "properties": {
                        "op_type": {
                            "type": "string",
                            "enum": ["MERGE", "GROUP", "MOVE"]
                        },
                        "ids": {
                            "type":
                            "array",
                            "items": {
                                "type": "string"
                            },
                            "description":
                            "MERGE至少2个LEAF ID；GROUP至少2个LEAF ID；MOVE仅限1个LEAF ID, id来自 [id: xxx] 中的 xxx",
                        },
                        "reasoning": {
                            "type": "string",
                            "description": "简要说明为什么执行此操作（中文）"
                        },
                        "name": {
                            "type":
                            "string",
                            "description":
                            "生成的节点系统名称。必须全小写英文，单词间用下划线连接(如 java_backend_specs)。勿用中文或特殊符号！",
                        },
                        "content": {
                            "type":
                            "string",
                            "description":
                            "仅 MERGE 和 GROUP 需要。MERGE: 原文细节的无损拼接或归纳（务必保留数值/专有名词）；GROUP: 新分类的主题概述。",
                        },
                        "path_to_move": {
                            "type":
                            "string",
                            "description":
                            "仅 MOVE 需要。目标分类的完整路径（必须从 <available_move_targets> 中精确复制）。",
                        },
                    },
                },
            },
            "overall_reasoning": {
                "type": "string",
                "description": "描述整体的整理策略和思考过程（中文）"
            },
            "updated_content": {
                "type": "string",
                "description": "当前目录在执行完上述 ops 后的全局最新摘要。用于被上级目录读取。",
            },
            "updated_name": {
                "type": "string",
                "description": "当前目录的新展示名（中文，可选）。仅在原名称不再适合当前内容时更新。",
            },
            "should_dirty_parent": {
                "type": "boolean",
                "description": "如果你在此次整理中得出了影响上级目录的重大新结论，设为 true 以触发语义上浮。"
            }
        },
    },
}
# ── Prompt 构建 ────────────────────────────────────────────────


def _format_node_list(nodes: list) -> str:

    if not nodes:
        return "  (空)"
    lines = []
    for n in nodes:
        lines.append(
            f"  - [id: {n.id[:8]}] node_type: {n.node_type.value} | name: {n.name}(not id) | content: {n.content}..."
        )
    return "\n".join(lines)


def _build_prompt(
    context: UpdateContext,
    max_nodes: int,
) -> Tuple[str, str]:

    all_nodes = list(context.active_nodes) + list(context.pending_nodes)
    total_count = len(all_nodes)

    sub_cats = [
        n for n in context.active_nodes if n.node_type == NodeType.CATEGORY
    ]
    available_paths = "\n".join([f"  * {c.path}"
                                 for c in sub_cats]) or "  (当前无子分类)"

    # 强化版的 System Prompt
    system_prompt = f"""你是一个运行在 SemaFS (语义文件系统) 底层的知识图谱调度引擎。
你的核心职责是：在保证【节点数不超过 {max_nodes} 个】的前提下，对当前的记忆碎片进行语义聚类和信息降维。

【核心算子 (Ops) 决策指南】
请严格根据以下场景选择操作：
1. 🟩 MERGE (合并叶子)：当几个节点描述的是【同一具体事物/习惯的不同侧面】（例："喜欢喝美式"与"喝咖啡不加糖"）。
   - ⚠️ 致命红线：MERGE 生成的 content 必须是所有原节点细节的「超集」。绝不允许丢失具体数值、时间、专有名词！可以将内容分段拼接，但不能用抽象废话替代具体细节。
2. 🗂️ GROUP (新建分类)：当几个节点属于【同一个宽泛主题】但互为独立实体（例："前端框架规范"与"后端DB规范"）。
   - 将它们移入新创建的 CATEGORY 中。新 content 是对该主题的精简摘要。
3. ➡️ MOVE (移动到现有)：当某个节点完全符合下方列出的「可用子分类」时使用。
   - ⚠️ 致命红线：path_to_move 必须一字不差地从可用列表中复制，绝不可凭空捏造路径！

【命名与格式红线】
- `name` 字段：必须作为有效的文件路径节点，尽可能一个单词表示，多个单词用下划线连接。仅限使用小写英文、数字和下划线 (a-z, 0-9, _)，不超过 32 字符。例如: coffee_prefs, morning_routine。绝对禁止中文、大写或空格。

【目录状态刷新】
- `updated_content`：你必须基于执行操作后的剩余节点和新节点，重新撰写当前目录的完整摘要。
- `should_dirty_parent`：如果本次整理提取出了全新的重要主题，或者改变了该目录的核心性质，设为 true 以触发级联更新。"""

    status_warning = ""
    if total_count > max_nodes:
        status_warning = f"🔴 严重警告：当前总节点数({total_count})已超出硬性上限({max_nodes})，你必须至少执行一次 MERGE 或 GROUP 操作来减少平行节点数量！"
    elif context.pending_nodes:
        status_warning = f"🟡 提示：有新碎片进入。如果总数逼近上限，请主动整理以保持目录清爽。"

    # 将内容呈现的结构更加清晰化
    user_content = f"""<directory_status>
- current_path: "{context.parent.path}"
- current_name: "{context.parent.display_name or context.parent.name}"
- capacity: {total_count}/{max_nodes}
- alert: {status_warning}
</directory_status>

<current_directory_summary>
{context.parent.content or '(空)'}
</current_directory_summary>

<available_move_targets>
{available_paths}
</available_move_targets>

<existing_active_nodes>
{_format_node_list(list(context.active_nodes))}
</existing_active_nodes>

<new_pending_fragments>
{_format_node_list(list(context.pending_nodes))}
</new_pending_fragments>

请综合以上信息，调用 `tree_ops` 输出你的重构计划。如果当前结构很健康且未超载，可以返回空的 ops 数组，但必须更新 updated_content。"""

    return (system_prompt, user_content)


class BaseLLMAdapter(ABC):
    """所有 LLM 适配器的基类，封装 prompt 构建和结果解析。"""

    @abstractmethod
    async def _call_api(self, system: str, user: str) -> Dict:
        """调用具体 LLM API，返回 tree_ops 的 input dict。"""
        ...

    async def call(self, context: UpdateContext, max_nodes: int) -> Dict:

        system, user = _build_prompt(context, max_nodes)
        try:
            return await self._call_api(system, user)
        except Exception as e:
            raise LLMAdapterError(f"LLM API 调用失败: {e}") from e
