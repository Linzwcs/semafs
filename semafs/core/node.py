from __future__ import annotations
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from .enums import NodeStatus, NodeType
from .exceptions import NodeTypeMismatchError

_VALID_SEGMENT = re.compile(r"^[a-z0-9_]+$")


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class NodePath:
    """
    路径值对象。不可变，相等性由值决定。

    设计原则：
    - 所有路径字符串操作有且只有一个家
    - 外部代码永远不需要 split('.') / rsplit('.') / startswith()
    - 非法路径在构造时即被清理，不会污染后续逻辑
    """
    _raw: str

    def __init__(self, raw: str) -> None:
        clean = re.sub(r"[^a-z0-9._]", "", raw.strip().lower()).strip(".")
        # 清理连续点、空段
        parts = [p for p in clean.split(".") if p]
        result = ".".join(parts) if parts else "root"
        object.__setattr__(self, "_raw", result)

    # ── 判断 ────────────────────────────────────────────────

    @property
    def is_root(self) -> bool:
        return self._raw == "root"

    def is_direct_child_of(self, other: "NodePath") -> bool:
        """self 是否是 other 的直接子节点。"""
        prefix = str(other) + "."
        if not self._raw.startswith(prefix):
            return False
        suffix = self._raw[len(prefix):]
        return "." not in suffix

    def is_descendant_of(self, other: "NodePath") -> bool:
        """self 是否是 other 的任意层级子孙。"""
        if self == other:
            return False
        return self._raw.startswith(str(other) + ".")

    # ── 导航 ────────────────────────────────────────────────

    @property
    def parent(self) -> "NodePath":
        if self.is_root:
            return self
        raw_parent = self._raw.rsplit(".", 1)[0]
        return NodePath(raw_parent)

    @property
    def name(self) -> str:
        """最后一段路径名，即节点在父目录中的 key。"""
        return self._raw.rsplit(".", 1)[-1]

    @property
    def parent_path_str(self) -> str:
        """
        兼容现有 TreeNode.parent_path 字段（str 类型）。
        root 的 parent_path 为空字符串。
        """
        if self.is_root:
            return ""
        return str(self.parent)

    @property
    def depth(self) -> int:
        return len(self._raw.split("."))

    def child(self, segment: str) -> "NodePath":
        """在当前路径下追加一段，返回子路径。"""
        clean_seg = re.sub(r"[^a-z0-9_]", "",
                           segment.lower().replace(" ", "_")).strip("_")
        if not clean_seg:
            raise ValueError(f"非法路径段: '{segment}'")
        return NodePath(f"{self._raw}.{clean_seg}")

    def sibling(self, segment: str) -> "NodePath":
        """返回同级路径。"""
        if self.is_root:
            return self.child(segment)
        return self.parent.child(segment)

    # ── 序列化 ──────────────────────────────────────────────

    def __str__(self) -> str:
        return self._raw

    def __repr__(self) -> str:
        return f"NodePath({self._raw!r})"

    # frozen=True 已自动生成 __hash__ 和 __eq__

    # ── 工厂方法 ────────────────────────────────────────────

    @classmethod
    def root(cls) -> "NodePath":
        return cls("root")

    @classmethod
    def from_parent_and_name(cls, parent_path: str, name: str) -> "NodePath":
        """从 (parent_path, name) 两字段重建完整路径，兼容现有数据模型。"""
        if not parent_path and name == "root":
            return cls.root()
        if not parent_path:
            return cls(name)
        return cls(f"{parent_path}.{name}")


@dataclass
class TreeNode:
    """
    统一节点模型。NodeType 枚举区分 CATEGORY / LEAF。

    为何不拆成两个类：
    - Python 的 isinstance 检查会散落在所有接受节点的函数里
    - list_children() 等接口返回类型会变成 List[BaseNode]，调用方到处强转
    - 现有数据库 schema 是单表，两类映射增加 ORM 复杂度
    用 assert/TypeGuard + 领域方法内部校验代替继承体系，同样安全。
    """
    parent_path: str
    name: str

    node_type: NodeType
    content: str = ""
    display_name: Optional[str] = None
    name_editable: bool = True
    payload: dict = field(default_factory=dict)
    tags: list = field(default_factory=list)

    status: NodeStatus = field(default=NodeStatus.ACTIVE)
    is_dirty: bool = False
    version: int = 1
    access_count: int = 0

    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    last_accessed_at: datetime = field(default_factory=_utcnow)

    _original_status: Optional[NodeStatus] = field(default=None,
                                                   repr=False,
                                                   init=False)

    # ── 主键
    id: str = field(default_factory=_new_id)

    def __post_init__(self) -> None:
        if self.node_type == NodeType.CATEGORY and not self.name:
            raise ValueError("CATEGORY 节点必须有 name")
        if self.node_type == NodeType.LEAF and not self.payload:
            # payload 是叶子节点的必要字段，空 dict 说明调用方忘记传了
            self.payload = {"_auto": True}

    # ── 路径属性 ────────────────────────────────────────────

    @property
    def node_path(self) -> NodePath:
        """返回强类型路径对象，所有路径操作都通过它。"""
        return NodePath.from_parent_and_name(self.parent_path, self.name)

    @property
    def path(self) -> str:
        """字符串路径，兼容现有代码和数据库查询。"""
        return str(self.node_path)

    @property
    def depth(self) -> int:
        return self.node_path.depth

    # ── 通用状态变更 ─────────────────────────────────────────

    def bump_version(self) -> None:
        self.version += 1
        self.updated_at = _utcnow()

    def touch(self) -> None:
        self.access_count += 1
        self.last_accessed_at = _utcnow()

    # ── 领域行为：CATEGORY 专属 ──────────────────────────────

    def receive_fragment(self) -> None:
        """
        领域规则：目录接收到一个新碎片（PENDING_REVIEW 叶子落入此目录）。
        目录自己决定：我需要被整理了。

        调用时机：apply_add_node 检测到新碎片挂入此目录时。
        不需要传入碎片对象——目录只关心"有新碎片来了"这个事实。
        """
        self._assert_category()
        if not self.is_dirty:
            self.is_dirty = True
            self.bump_version()

    def apply_plan_result(
        self,
        content: str = None,
        name: Optional[str] = None,
    ) -> Optional[str]:

        self._assert_category()

        if content is not None:
            self.content = content

        old_path_str = None
        if name is not None and self.name_editable and name != self.name:
            old_path_str = self.path
            self.name = name

        self.is_dirty = False
        self.payload.pop("_force_llm", None)

        self.bump_version()
        return old_path_str

    def request_semantic_rethink(self) -> None:

        self._assert_category()
        self.is_dirty = True
        self.payload["_force_llm"] = True
        self.bump_version()

    @classmethod
    def new_category(
        cls,
        path: NodePath,
        content: str = "",
        display_name: Optional[str] = None,
        name_editable: bool = True,
    ) -> "TreeNode":
        return cls(
            parent_path=path.parent_path_str,
            name=path.name,
            node_type=NodeType.CATEGORY,
            content=content,
            display_name=display_name,
            name_editable=name_editable,
            payload={},
        )

    @classmethod
    def new_leaf(
        cls,
        path: NodePath,
        content: str,
        payload: Optional[dict] = None,
        tags: Optional[list] = None,
        status: NodeStatus = NodeStatus.ACTIVE,
    ) -> "TreeNode":
        return cls(
            parent_path=path.parent_path_str,
            name=path.name,
            node_type=NodeType.LEAF,
            content=content,
            payload=payload or {"_leaf": True},
            tags=tags or [],
            status=status,
        )

    @classmethod
    def new_fragment(
        cls,
        parent_path: NodePath,
        content: str,
        payload: Optional[dict] = None,
    ) -> "TreeNode":
        """
        工厂方法：创建一个待整理碎片（PENDING_REVIEW）。
        name 由系统自动生成，调用方不需要（也不应该）指定。
        """
        frag_id = uuid.uuid4().hex[:8]
        real_payload = dict(payload or {})
        real_payload["_created_at"] = _utcnow().isoformat()

        return cls(
            parent_path=str(parent_path),
            name=f"_frag_{frag_id}",
            node_type=NodeType.LEAF,
            content=content,
            payload=real_payload,
            status=NodeStatus.PENDING_REVIEW,
            name_editable=False,
        )

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
            "updated_at": self.updated_at.isoformat(),
        }

    def start_processing(self) -> None:
        """
        进入思考状态（挂牌）。
        对外界暴露，表示大模型正在处理此节点。
        """
        if self.status in (NodeStatus.ARCHIVED, NodeStatus.PROCESSING):
            return  # 忽略无效流转

        self._original_status = self.status
        self.status = NodeStatus.PROCESSING
        self.bump_version()

    def finish_processing(self) -> None:
        """
        结束思考状态（摘牌）。
        存活下来的节点（没有被归档的）统一升格为 ACTIVE。
        """
        if self.status != NodeStatus.PROCESSING:
            return

        self.status = NodeStatus.ACTIVE
        self._original_status = None
        self.bump_version()

    def fail_processing(self) -> None:
        """
        思考失败（回滚）。
        退回到进入 PROCESSING 之前的状态。
        """
        if self.status == NodeStatus.PROCESSING and self._original_status:
            self.status = self._original_status
            self._original_status = None
            self.bump_version()

    def archive(self) -> None:

        self._assert_leaf()
        if self.status == NodeStatus.ARCHIVED:
            return
        self.status = NodeStatus.ARCHIVED
        self._original_status = None
        self.bump_version()

    def _assert_category(self) -> None:
        if self.node_type != NodeType.CATEGORY:
            raise NodeTypeMismatchError(self.path, "CATEGORY",
                                        self.node_type.value)

    def _assert_leaf(self) -> None:
        if self.node_type != NodeType.LEAF:
            raise NodeTypeMismatchError(self.path, "LEAF",
                                        self.node_type.value)

    def __repr__(self) -> str:
        return (f"<TreeNode {self.node_type.value} "
                f"path={self.path!r} "
                f"status={self.status.value} "
                f"id={self.id[:8]}>")
