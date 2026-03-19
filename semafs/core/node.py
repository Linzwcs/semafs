"""Node - The fundamental content container in SemaFS."""

import re
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Optional
from uuid import uuid4

from .naming import normalize_name

_VALID_NAME_RE = re.compile(r"^[a-z0-9_]+$")


class NodeType(Enum):
    """Node type enumeration."""
    CATEGORY = "category"
    LEAF = "leaf"


class NodeStage(Enum):
    """Node lifecycle stage."""
    ACTIVE = "active"
    PENDING = "pending"
    COLD = "cold"          # Rolled up, retrievable but excluded from maintenance
    ARCHIVED = "archived"


@dataclass(frozen=True)
class NodePath:
    """Immutable path value object."""

    value: str

    def __post_init__(self):
        """Validate path format."""
        if not self.value:
            raise ValueError("Path cannot be empty")
        if self.value == "root":
            return
        if not re.match(r'^root\.[a-z0-9_]+(\.[a-z0-9_]+)*$', self.value):
            raise ValueError(
                f"Invalid path: {self.value}. "
                "Must start with 'root.' and contain only lowercase "
                "letters, numbers, underscores, and dots"
            )

    @classmethod
    def root(cls) -> "NodePath":
        """Create root path."""
        return cls("root")

    @classmethod
    def from_parent_and_name(cls, parent_path: str, name: str) -> "NodePath":
        """Create path from parent and name."""
        if not parent_path:
            if name == "root":
                return cls.root()
            return cls(f"root.{name}")
        if parent_path == "root":
            return cls(f"root.{name}")
        return cls(f"{parent_path}.{name}")

    @property
    def parent(self) -> Optional["NodePath"]:
        """Get parent path."""
        if self.value == "root":
            return None
        return NodePath(self.value.rsplit(".", 1)[0])

    @property
    def parent_str(self) -> str:
        """Get parent path as string (empty string for root-level nodes)."""
        p = self.parent
        if p is None:
            return ""
        return p.value

    @property
    def name(self) -> str:
        """Get node name (last component)."""
        if self.value == "root":
            return "root"
        return self.value.rsplit(".", 1)[-1]

    @property
    def depth(self) -> int:
        """Get depth in tree (root = 0)."""
        if self.value == "root":
            return 0
        return self.value.count(".")

    def child(self, name: str) -> "NodePath":
        """Create child path."""
        return NodePath(f"{self.value}.{name}")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Node:
    """
    Immutable content container.

    Design principles:
    - Frozen dataclass (immutable)
    - Content for leaves, summary for categories
    - Stage tracks lifecycle (ACTIVE vs PENDING)
    """

    id: str
    parent_id: Optional[str]
    name: str
    canonical_path: str
    node_type: NodeType
    content: Optional[str] = None   # Only for leaves
    summary: Optional[str] = None   # Only for categories
    category_meta: dict = field(default_factory=dict)  # Only for categories
    payload: dict = field(default_factory=dict)
    tags: tuple[str, ...] = field(default_factory=tuple)
    stage: NodeStage = NodeStage.ACTIVE
    skeleton: bool = False
    name_editable: bool = True

    @staticmethod
    def normalize_name(
        raw_name: str,
        *,
        fallback_prefix: str = "node",
    ) -> str:
        """
        Normalize arbitrary LLM/user-provided names into valid node names.

        Rules:
        - lowercase ascii letters / digits / underscore only
        - collapse repeated separators
        - fallback to <prefix>_<6hex> if empty after normalization
        """
        return normalize_name(raw_name, fallback_prefix=fallback_prefix)

    def __post_init__(self):
        """Validate node invariants."""
        if not self.canonical_path:
            raise ValueError("canonical_path cannot be empty")
        # Path validation remains centralized in NodePath.
        NodePath(self.canonical_path)
        if self.node_type == NodeType.LEAF and self.content is None:
            raise ValueError("Leaf nodes must have content")
        if self.node_type == NodeType.CATEGORY and self.summary is None:
            raise ValueError("Category nodes must have summary")
        if self.node_type == NodeType.LEAF and self.category_meta:
            raise ValueError("Leaf nodes cannot have category_meta")
        if self.node_type == NodeType.LEAF and self.skeleton:
            raise ValueError("Leaf nodes cannot be skeleton nodes")
        if self.node_type == NodeType.LEAF and not self.name_editable:
            raise ValueError("Leaf nodes must be name-editable")
        if self.skeleton and self.name_editable:
            raise ValueError("Skeleton nodes must have non-editable names")
        if not _VALID_NAME_RE.match(self.name):
            raise ValueError(
                f"Invalid name: {self.name}. "
                "Must contain only lowercase letters, numbers, and underscores"
            )

    @classmethod
    def create_root(cls) -> "Node":
        """Create root category node."""
        return cls(
            id=str(uuid4()),
            parent_id=None,
            name="root",
            canonical_path="root",
            node_type=NodeType.CATEGORY,
            summary="Root of knowledge tree",
            skeleton=True,
            name_editable=False,
        )

    @classmethod
    def create_category(
        cls,
        parent_id: str,
        parent_path: str,
        name: str,
        summary: str,
        category_meta: Optional[dict] = None,
        payload: Optional[dict] = None,
        tags: Optional[tuple[str, ...]] = None,
        skeleton: bool = False,
        name_editable: bool = True,
    ) -> "Node":
        """Create a new category node."""
        normalized_name = cls.normalize_name(name, fallback_prefix="category")
        return cls(
            id=str(uuid4()),
            parent_id=parent_id,
            name=normalized_name,
            canonical_path=NodePath.from_parent_and_name(
                parent_path, normalized_name
            ).value,
            node_type=NodeType.CATEGORY,
            summary=summary,
            category_meta=category_meta or {},
            payload=payload or {},
            tags=tags or (),
            skeleton=skeleton,
            name_editable=name_editable,
        )

    @classmethod
    def create_leaf(
        cls,
        parent_id: str,
        parent_path: str,
        name: str,
        content: str,
        payload: Optional[dict] = None,
        tags: Optional[tuple[str, ...]] = None,
        stage: NodeStage = NodeStage.ACTIVE,
    ) -> "Node":
        """Create a new leaf node."""
        normalized_name = cls.normalize_name(name, fallback_prefix="leaf")
        return cls(
            id=str(uuid4()),
            parent_id=parent_id,
            name=normalized_name,
            canonical_path=NodePath.from_parent_and_name(
                parent_path, normalized_name
            ).value,
            node_type=NodeType.LEAF,
            content=content,
            category_meta={},
            payload=payload or {},
            tags=tags or (),
            stage=stage,
            skeleton=False,
            name_editable=True,
        )

    @property
    def path(self) -> NodePath:
        """Get full path of this node."""
        return NodePath(self.canonical_path)

    @property
    def parent_path(self) -> str:
        """Computed parent path for read compatibility."""
        return self.path.parent_str

    def with_summary(self, summary: str) -> "Node":
        """Create a copy with updated summary (categories only)."""
        if self.node_type != NodeType.CATEGORY:
            raise ValueError("Only categories can have summaries")
        return replace(self, summary=summary)

    def with_category_meta(self, category_meta: dict) -> "Node":
        """Create a copy with updated category metadata."""
        if self.node_type != NodeType.CATEGORY:
            raise ValueError("Only categories can have category metadata")
        return replace(self, category_meta=category_meta)

    def with_name(self, name: str) -> "Node":
        """Create a copy with updated name."""
        if not self.name_editable:
            raise ValueError(f"Node name is locked: {self.path.value}")
        normalized_name = self.normalize_name(name)
        return replace(self, name=normalized_name)

    def with_name_editable(self, editable: bool) -> "Node":
        """Create a copy with updated name editability."""
        if self.node_type == NodeType.LEAF and not editable:
            raise ValueError("Leaf nodes must be name-editable")
        if self.skeleton and editable:
            raise ValueError("Skeleton nodes must have non-editable names")
        return replace(self, name_editable=editable)

    def with_skeleton(self, skeleton: bool) -> "Node":
        """Create a copy with updated skeleton flag."""
        if self.node_type != NodeType.CATEGORY and skeleton:
            raise ValueError("Only category nodes can be skeleton nodes")
        if skeleton:
            return replace(self, skeleton=True, name_editable=False)
        return replace(self, skeleton=False)

    def with_parent(self, parent_id: str, parent_path: str) -> "Node":
        """Create a copy with updated parent identity and path projection."""
        new_path = NodePath.from_parent_and_name(parent_path, self.name).value
        return replace(self, parent_id=parent_id, canonical_path=new_path)

    def with_path_projection(self, canonical_path: str) -> "Node":
        """Create a copy with refreshed path projection."""
        return replace(self, canonical_path=canonical_path)

    def with_stage(self, stage: NodeStage) -> "Node":
        """Create a copy with updated stage."""
        return replace(self, stage=stage)

    def with_payload(self, payload: dict) -> "Node":
        """Create a copy with updated payload."""
        return replace(self, payload=payload)
