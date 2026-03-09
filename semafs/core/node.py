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
    _raw: str

    def __init__(self, raw: str) -> None:
        clean = re.sub(r"[^a-z0-9._]", "", raw.strip().lower()).strip(".")
        parts = [p for p in clean.split(".") if p]
        result = ".".join(parts) if parts else "root"
        object.__setattr__(self, "_raw", result)

    @property
    def is_root(self) -> bool:
        return self._raw == "root"

    def is_direct_child_of(self, other: "NodePath") -> bool:
        prefix = str(other) + "."
        if not self._raw.startswith(prefix): return False
        return "." not in self._raw[len(prefix):]

    def is_descendant_of(self, other: "NodePath") -> bool:
        if self == other: return False
        return self._raw.startswith(str(other) + ".")

    @property
    def parent(self) -> "NodePath":
        if self.is_root: return self
        return NodePath(self._raw.rsplit(".", 1)[0])

    @property
    def name(self) -> str:
        return self._raw.rsplit(".", 1)[-1]

    @property
    def parent_path_str(self) -> str:
        if self.is_root: return ""
        return str(self.parent)

    @property
    def depth(self) -> int:
        return len(self._raw.split("."))

    def child(self, segment: str) -> "NodePath":
        clean_seg = re.sub(r"[^a-z0-9_]", "",
                           segment.lower().replace(" ", "_")).strip("_")
        if not clean_seg:
            raise ValueError(f"非法路径段: '{segment}'")
        return NodePath(f"{self._raw}.{clean_seg}")

    def sibling(self, segment: str) -> "NodePath":
        if self.is_root: return self.child(segment)
        return self.parent.child(segment)

    def __str__(self) -> str:
        return self._raw

    def __repr__(self) -> str:
        return f"NodePath({self._raw!r})"

    @classmethod
    def root(cls) -> "NodePath":
        return cls("root")

    @classmethod
    def from_parent_and_name(cls, parent_path: str, name: str) -> "NodePath":
        if not parent_path and name == "root":
            return cls.root()
        if not parent_path:
            return cls(name)
        return cls(f"{parent_path}.{name}")


@dataclass
class TreeNode:
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
    id: str = field(default_factory=_new_id)

    def __post_init__(self) -> None:
        if self.node_type == NodeType.CATEGORY and not self.name:
            raise ValueError("CATEGORY 节点必须有 name")
        if self.node_type == NodeType.LEAF and not self.payload:
            self.payload = {"_auto": True}

    @property
    def node_path(self) -> NodePath:
        return NodePath.from_parent_and_name(self.parent_path, self.name)

    @property
    def path(self) -> str:
        return str(self.node_path)

    @property
    def depth(self) -> int:
        return self.node_path.depth

    def bump_version(self) -> None:
        self.version += 1
        self.updated_at = _utcnow()

    def touch(self) -> None:
        self.access_count += 1
        self.last_accessed_at = _utcnow()

    def receive_fragment(self) -> None:
        self._assert_category()
        if not self.is_dirty:
            self.is_dirty = True
            self.bump_version()

    def apply_plan_result(self,
                          content: str = None,
                          name: Optional[str] = None) -> Optional[str]:
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
    def new_category(cls,
                     path: NodePath,
                     content: str = "",
                     display_name: Optional[str] = None,
                     name_editable: bool = True,
                     status: NodeStatus = NodeStatus.ACTIVE) -> "TreeNode":
        return cls(parent_path=path.parent_path_str,
                   name=path.name,
                   node_type=NodeType.CATEGORY,
                   content=content,
                   display_name=display_name,
                   name_editable=name_editable,
                   payload={},
                   status=status)

    @classmethod
    def new_leaf(cls,
                 path: NodePath,
                 content: str,
                 payload: Optional[dict] = None,
                 tags: Optional[list] = None,
                 status: NodeStatus = NodeStatus.ACTIVE) -> "TreeNode":
        return cls(parent_path=path.parent_path_str,
                   name=path.name,
                   node_type=NodeType.LEAF,
                   content=content,
                   payload=payload or {"_leaf": True},
                   tags=tags or [],
                   status=status)

    @classmethod
    def new_fragment(cls,
                     parent_path: NodePath,
                     content: str,
                     payload: Optional[dict] = None) -> "TreeNode":
        frag_id = uuid.uuid4().hex[:8]
        real_payload = dict(payload or {})
        real_payload["_created_at"] = _utcnow().isoformat()
        return cls(parent_path=str(parent_path),
                   name=f"_frag_{frag_id}",
                   node_type=NodeType.LEAF,
                   content=content,
                   payload=real_payload,
                   status=NodeStatus.PENDING_REVIEW,
                   name_editable=False)

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
            "updated_at": self.updated_at.isoformat()
        }

    def start_processing(self) -> None:
        if self.status in (NodeStatus.ARCHIVED, NodeStatus.PROCESSING): return
        self._original_status = self.status
        self.status = NodeStatus.PROCESSING
        self.bump_version()

    def finish_processing(self) -> None:
        if self.status != NodeStatus.PROCESSING: return
        self.status = NodeStatus.ACTIVE
        self._original_status = None
        self.bump_version()

    def fail_processing(self) -> None:
        if self.status == NodeStatus.PROCESSING and self._original_status:
            self.status = self._original_status
            self._original_status = None
            self.bump_version()

    def archive(self) -> None:
        self._assert_leaf()
        if self.status == NodeStatus.ARCHIVED: return
        self.status = NodeStatus.ARCHIVED
        self._original_status = None
        self.bump_version()

    def clear_dirty(self) -> None:
        # FIX Bug 5: clear_dirty is CATEGORY-only; guard against LEAF misuse
        self._assert_category()
        self.is_dirty = False
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
        return f"<TreeNode {self.node_type.value} path={self.path!r} status={self.status.value} id={self.id[:8]}>"
