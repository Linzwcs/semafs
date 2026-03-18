"""Node - The fundamental content container in SemaFS."""

import re
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Optional
from uuid import uuid4


class NodeType(Enum):
    """Node type enumeration."""
    CATEGORY = "category"
    LEAF = "leaf"


class NodeStage(Enum):
    """Node lifecycle stage."""
    ACTIVE = "active"
    PENDING = "pending"


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
        if not re.match(r'^[a-z0-9_]+(\.[a-z0-9_]+)*$', self.value):
            raise ValueError(
                f"Invalid path: {self.value}. "
                "Must contain only lowercase letters, numbers, "
                "underscores, and dots"
            )

    @classmethod
    def root(cls) -> "NodePath":
        """Create root path."""
        return cls("root")

    @classmethod
    def from_parent_and_name(cls, parent_path: str, name: str) -> "NodePath":
        """Create path from parent and name."""
        if parent_path == "root" or not parent_path:
            return cls(name)
        return cls(f"{parent_path}.{name}")

    @property
    def parent(self) -> Optional["NodePath"]:
        """Get parent path."""
        if self.value == "root":
            return None
        if "." not in self.value:
            return NodePath.root()
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
        return self.value.count(".") + 1

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
    payload: dict = field(default_factory=dict)
    tags: tuple[str, ...] = field(default_factory=tuple)
    stage: NodeStage = NodeStage.ACTIVE

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
        if not re.match(r'^[a-z0-9_]+$', self.name):
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
        )

    @classmethod
    def create_category(
        cls,
        parent_id: str,
        parent_path: str,
        name: str,
        summary: str,
        payload: Optional[dict] = None,
        tags: Optional[tuple[str, ...]] = None,
    ) -> "Node":
        """Create a new category node."""
        return cls(
            id=str(uuid4()),
            parent_id=parent_id,
            name=name,
            canonical_path=NodePath.from_parent_and_name(
                parent_path, name
            ).value,
            node_type=NodeType.CATEGORY,
            summary=summary,
            payload=payload or {},
            tags=tags or (),
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
        return cls(
            id=str(uuid4()),
            parent_id=parent_id,
            name=name,
            canonical_path=NodePath.from_parent_and_name(
                parent_path, name
            ).value,
            node_type=NodeType.LEAF,
            content=content,
            payload=payload or {},
            tags=tags or (),
            stage=stage,
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

    def with_name(self, name: str) -> "Node":
        """Create a copy with updated name."""
        return replace(self, name=name)

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
