"""
领域层：操作命令（Op）与计划（RebalancePlan）

设计原则：
1. Op 是纯数据载体（frozen dataclass），不包含任何执行逻辑
2. LLM 的输出被解析成 RebalancePlan，PlanExecutor 负责执行
3. ids 是操作的对象列表，content/name/path 是 LLM 决定的语义信息
4. 没有任何一个 Op 知道"怎么做"，只知道"做什么"
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple, Union

from .enums import OpType


@dataclass(frozen=True)
class MergeOp:
    """
    合并：将 ids 里的多个叶子归档，创建一个新的合并叶子。

    - ids: 至少 2 个叶子节点 ID（LLM 选择的合并对象）
    - content: LLM 生成的语义浓缩内容（不是原内容的简单拼接）
    - name: 新叶子的路径名（LLM 生成，英文，下划线分隔）
    - reasoning: LLM 的决策理由，用于审计日志
    """
    ids: Tuple[str, ...]
    content: str
    name: str
    reasoning: str = ""
    op_type: OpType = field(default=OpType.MERGE, init=False)

    def __post_init__(self) -> None:
        if len(self.ids) < 2:
            raise ValueError(f"MergeOp 至少需要 2 个节点 ID，收到 {len(self.ids)} 个")


@dataclass(frozen=True)
class GroupOp:
    """
    分组：将 ids 里的叶子归入一个新建的子 CATEGORY。

    - ids: 至少 2 个叶子节点 ID（构成新子目录的内容）
    - name: 新 CATEGORY 的路径名（LLM 生成）
    - content: 新 CATEGORY 的摘要（LLM 从 ids 内容语义浓缩）
    """
    ids: Tuple[str, ...]
    name: str
    content: str = ""
    reasoning: str = ""
    op_type: OpType = field(default=OpType.GROUP, init=False)

    def __post_init__(self) -> None:
        if len(self.ids) < 2:
            raise ValueError(f"GroupOp 至少需要 2 个节点 ID，收到 {len(self.ids)} 个")
        if not self.name:
            raise ValueError("GroupOp 必须提供新 CATEGORY 的 name")


@dataclass(frozen=True)
class MoveOp:
    """
    移动：将单个叶子移入已存在的目标 CATEGORY。

    - ids: 恰好 1 个叶子节点 ID
    - path_to_move: 目标 CATEGORY 的完整路径（必须已存在，不能自动创建）
    - name: 移入后叶子的路径名（LLM 生成）
    """
    ids: Tuple[str, ...]
    path_to_move: str
    name: str
    reasoning: str = ""
    op_type: OpType = field(default=OpType.MOVE, init=False)

    def __post_init__(self) -> None:
        if len(self.ids) != 1:
            raise ValueError(f"MoveOp 只能移动 1 个节点，收到 {len(self.ids)} 个")
        if not self.path_to_move:
            raise ValueError("MoveOp 必须提供 path_to_move")


@dataclass(frozen=True)
class PersistOp:
    """
    持久化：规则策略专用，将 PENDING_REVIEW 碎片直接转为 ACTIVE 叶子。
    不涉及 LLM，不需要 content/name 的语义决策。
    """
    ids: Tuple[str, ...]
    name: str
    content: str
    payload: dict
    reasoning: str = "规则策略：归档 inbox 碎片"
    op_type: OpType = field(default=OpType.PERSIST, init=False)

    def __post_init__(self) -> None:
        if len(self.ids) != 1:
            raise ValueError("PersistOp 一次只处理 1 个节点")


AnyOp = Union[MergeOp, GroupOp, MoveOp, PersistOp]


@dataclass(frozen=True)
class RebalancePlan:
    """
    LLM 大脑深思熟虑后输出的整理计划书。

    - ops: 有序操作列表，PlanExecutor 按序执行
    - updated_content: 执行完毕后目录的新摘要（LLM 语义浓缩）
    - updated_name: 目录的新展示名（可选，LLM 认为有必要时才提供）
    - overall_reasoning: LLM 整体决策理由
    - is_llm_plan: True 表示来自 LLM，False 表示规则策略降级
    - should_parent_be_dirty: 是否需要将父目录标记为 dirty，默认 True

    空计划（ops=[]）合法：表示 LLM 认为当前目录不需要整理，
    但仍需更新 updated_content（目录摘要可能需要刷新）。
    """
    ops: Tuple[AnyOp, ...]
    updated_content: str
    updated_name: Optional[str] = None
    overall_reasoning: str = ""
    should_dirty_parent: bool = False
    is_llm_plan: bool = True

    @property
    def is_empty(self) -> bool:
        """没有结构变更，只更新摘要。"""
        return len(self.ops) == 0

    @property
    def ops_summary(self) -> str:
        if self.is_empty:
            return "(仅更新摘要)"
        counts: dict[str, int] = {}
        for op in self.ops:
            k = op.op_type.value
            counts[k] = counts.get(k, 0) + 1
        return " | ".join(f"{k}×{v}" for k, v in counts.items())


@dataclass(frozen=True)
class UpdateContext:
    """
    整理上下文：PlanExecutor 和 LLMStrategy 所需的全部信息快照。

    这是一个只读的数据快照，在事务开始时一次性获取，
    后续操作基于此快照推演，避免在执行中途读库产生的不一致。
    """
    from .node import TreeNode  # 避免循环导入，延迟引入

    parent: "TreeNode"
    active_nodes: Tuple["TreeNode", ...]  # 已整理的稳定节点
    pending_nodes: Tuple["TreeNode", ...]  # 刚写入的碎片（PENDING_REVIEW）

    @property
    def inbox(self) -> Tuple["TreeNode", ...]:
        """pending_nodes 的语义别名。"""
        return self.pending_nodes

    @property
    def children(self) -> Tuple["TreeNode", ...]:
        """active_nodes 的语义别名。"""
        return self.active_nodes

    @property
    def all_nodes(self) -> Tuple["TreeNode", ...]:
        return self.active_nodes + self.pending_nodes
