from __future__ import annotations
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from .enums import NodeStatus, NodeType

_PATH_RE = re.compile(r"^[a-z0-9]+(\.[a-z0-9_]+)*$")


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def validate_path(path: str) -> str:
    """路径清理与验证，符合 ltree 风格。"""
    clean = re.sub(r"[^a-z0-9._]", "", path.lower()).strip(".")
    if not clean or not _PATH_RE.match(clean):
        raise ValueError(f"非法树路径: '{path}' (清理后: '{clean}')")
    return clean


@dataclass
class TreeNode:

    parent_path: str
    name: str
    node_type: NodeType
    content: str = ""
    tags: list = field(default_factory=list)
    payload: dict = field(default_factory=dict)
    display_name: Optional[str] = None
    name_editable: bool = True
    status: NodeStatus = field(default=NodeStatus.ACTIVE)
    is_dirty: bool = False
    version: int = 1
    access_count: int = 0
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    last_accessed_at: datetime = field(default_factory=_utcnow)
    id: str = field(default_factory=_new_id)

    @classmethod
    def from_path(cls, path: str, **kwargs: Any) -> TreeNode:
        """从完整路径创建，path 拆为 (parent_path, name)。"""
        from ..utils import path_to_parent_and_segment
        pp, seg = path_to_parent_and_segment(validate_path(path))
        return cls(parent_path=pp, name=seg, **kwargs)

    def __post_init__(self) -> None:
        if self.node_type == NodeType.CATEGORY and not self.name:
            raise ValueError("CATEGORY 节点必须提供 name")
        if self.node_type == NodeType.LEAF and not self.payload:
            raise ValueError("LEAF 节点必须提供 payload")

    @property
    def path(self) -> str:
        """完整路径，path=parent_path.name。"""
        if self.parent_path == "" and self.name == "root":
            return "root"
        return f"{self.parent_path}.{self.name}" if self.parent_path else self.name

    @property
    def depth(self) -> int:
        """路径深度。"""
        return len(self.path.split("."))

    def touch(self) -> None:

        self.access_count += 1
        self.last_accessed_at = _utcnow()

    def bump_version(self) -> None:
        self.version += 1
        self.updated_at = _utcnow()

    def to_dict(self) -> dict:

        return {
            "id": self.id,
            "path": self.path,
            "node_type": self.node_type.value,
            "status": self.status.value,
            "name": self.display_name or self.name,
            "name_editable": self.name_editable,
            "content": self.content,
            "payload": self.payload,
            "tags": self.tags,
            "is_dirty": self.is_dirty,
            "version": self.version,
            "access_count": self.access_count,
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self) -> str:
        t, p, i = self.node_type.value, self.path, self.id[:8]
        return f"<TreeNode {t} path={p!r} id={i}>"


class VirtualTreeNode(TreeNode):

    node_type: NodeType = field(default=NodeType.LEAF)
    status: NodeStatus = field(default=NodeStatus.PENDING_REVIEW)
    name_editable: bool = field(default=False, init=False)  # 虚拟节点名由系统生成，不可改
    retry_count: int = 0

    @classmethod
    def create(
        cls,
        parent_path: str,
        content: str,
        payload: dict = None,
    ) -> VirtualTreeNode:
        """
        工厂方法：快速创建一个挂载在 parent_path 下的虚拟节点。
        path=目录，name=_frag_xxx（段名）。
        """
        frag_id = uuid.uuid4().hex[:8]
        name = f"_virtual_{frag_id}"

        real_payload = payload or {}
        real_payload["_is_virtual"] = True
        real_payload["_created_at"] = _utcnow().isoformat()

        return cls(
            parent_path=parent_path,
            name=name,
            node_type=NodeType.LEAF,
            content=content,
            payload=real_payload,
            status=NodeStatus.PENDING_REVIEW,
        )

    def __post_init__(self) -> None:
        # 确保 payload 中有标记
        if "_is_virtual" not in self.payload:
            self.payload["_is_virtual"] = True

    def mark_processing(self) -> None:
        """只是一个语义化的 Helper，实际修改状态需要通过 Repo 保存"""
        # 注意：dataclass 若 frozen=True 则不能直接改，这里假设是非 frozen
        # 实际业务中状态流转通常由 Repo 处理
        pass
