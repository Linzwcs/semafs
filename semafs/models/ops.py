from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Union, Dict, Any, Tuple
from .enums import OpType
from .nodes import TreeNode


@dataclass(frozen=True)
class Op(ABC):

    ids: Tuple[str, ...]
    reasoning: str
    op_type: OpType

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """序列化为可持久化字典，用于 AuditLog 审计日志。"""
        return {
            "op_type": self.op_type.value,
            "ids": list(self.ids),
            "reasoning": self.reasoning,
        }


@dataclass(frozen=True)
class MoveOp(Op):
    """一次仅移动一个叶子节点。ids 必须包含且仅包含一个叶子节点 ID。"""

    path_to_move: str  # 目标 category 路径，必须已存在；不能自动创建
    name: Optional[str] = None  # 移入后的叶子节点名，LLM 配套生成
    op_type: OpType = field(default=OpType.MOVE, init=False)

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d["path_to_move"] = self.path_to_move
        if self.name is not None:
            d["name"] = self.name
        return d


@dataclass(frozen=True)
class MergeOp(Op):
    """合并 ids 中的叶子，父路径由首节点 parent_path 决定。"""

    content: str
    name: Optional[str] = None
    op_type: OpType = field(default=OpType.MERGE, init=False)

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d["content"] = self.content
        if self.name is not None:
            d["name"] = self.name
        return d


@dataclass(frozen=True)
class SplitOp(Op):
    """
    创建子树：新建 category 将 ids 移入其下。父路径由执行上下文（当前维护的目录）决定。
    """

    name: str  # 新 category 名称，完整路径 = 父目录.name
    content: str = ""  # LLM 根据 ids 生成的语义摘要
    op_type: OpType = field(default=OpType.SPLIT, init=False)

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d["name"] = self.name
        if self.content:
            d["content"] = self.content
        return d


@dataclass(frozen=True)
class PersistenceOp(Op):

    name: str
    content: str
    payload: dict
    op_type: OpType = field(default=OpType.PERSISTENCE, init=False)

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d["name"] = self.name
        return d


AnyOp = Union[MoveOp, MergeOp, SplitOp, PersistenceOp]


@dataclass
class NodeUpdateOp:
    """
    维护一个 Category 节点。
    - ops: 对其子节点的操作（MERGE/SPLIT/MOVE）
    不暴露 path，执行时由调用方传入 category_path。
    """

    ops: List[AnyOp]
    updated_content: str
    updated_name: Optional[str] = None
    is_macro_change: bool = False
    overall_reasoning: str = ""

    @property
    def ops_summary(self) -> str:
        if not self.ops:
            return "(仅更新 content)"

        counts: Dict[str, int] = {}
        for a in self.ops:
            k = a.op_type.value
            counts[k] = counts.get(k, 0) + 1

        return " | ".join(f"{k}×{v}" for k, v in counts.items())

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "ops": [a.to_dict() for a in self.ops],
            "updated_content": self.updated_content,
            "is_macro_change": self.is_macro_change,
            "overall_reasoning": self.overall_reasoning,
        }
        if self.updated_name is not None:
            d["updated_name"] = self.updated_name
        return d


@dataclass(frozen=True)
class NodeUpdateContext:
    parent: TreeNode
    active_nodes: List[TreeNode]  # 已整理的记忆
    pending_nodes: List[TreeNode]  # 刚写进来的碎片记忆

    @property
    def inbox(self) -> List[TreeNode]:
        """与 pending_nodes 同义，供策略/维护逻辑使用。"""
        return self.pending_nodes

    @property
    def children(self) -> List[TreeNode]:
        """与 active_nodes 同义，供策略/维护逻辑使用。"""
        return self.active_nodes


@dataclass
class TreeOpsTxn:

    nodes_to_update: List = field(default_factory=list)
    nodes_to_archive_ids: List[str] = field(default_factory=list)
    inbox_ids_to_resolve: List[str] = field(default_factory=list)
    dirty_ancestor_paths: List[str] = field(default_factory=list)
    audit_snapshot: Dict[str, Any] = field(default_factory=dict)
